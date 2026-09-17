#!/usr/bin/env python3
"""
Buscador de Importadores Similares - PR/SC
===========================================
Uso:
    pip install requests duckdb
    python buscador_importadores.py <CNPJ1> <CNPJ2> <CNPJ3>

    --profile       Apenas perfil (sem baixar dados)
    --shallow N     Baixa apenas N arquivos (~3min cada) para resposta rapida
    --db-url URL    Baixa um DuckDB pre-pronto (evita download de 6.5GB)

Exemplo:
    python buscador_importadores.py 11378117000120 33000167000101 27865757000102
    python buscador_importadores.py --shallow 2 11378117000120 33000167000101 27865757000102
"""

import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import os
import duckdb
import requests

# ─── CONFIG ───────────────────────────────────────────────────────────────────
# APIs de exemplo — troque via variáveis de ambiente para uso real
# Antes: APIs reais — agora configuráveis via env

OPENCNPJ_URL = os.getenv("CNPJ_API_URL", "https://api.exemplo.com/cnpj/{}")
DADOS_URL = os.getenv("DADOS_RF_URL", "https://api.exemplo.com/dados-rf/arquivos/")
LATEST = os.getenv("DADOS_RF_LATEST", "2026-05-10")

CACHE = Path.home() / ".cache" / "cnpj_rfb"
DB_FILE = CACHE / "cnpj.db"
EMPRESAS_DIR = CACHE / "empresas_zips"
ESTAB_CACHE = CACHE / "estab_pr_sc.csv"

CNAE_IMP = [str(i) for i in range(46, 51)]
SIT_ATIVA = "02"
CAP_MIN_FATOR = 0.3
CAP_MAX_FATOR = 3.0
LIMITE = 15

ESTAB_ZIPS = [f"Estabelecimentos{i}.zip" for i in range(10)]
EMPRESAS_ZIPS = [f"Empresas{i}.zip" for i in range(10)]

ESTAB_COLS = {
    "cnpj_basico": "VARCHAR", "cnpj_ordem": "VARCHAR", "cnpj_dv": "VARCHAR",
    "matriz_filial": "VARCHAR", "nome_fantasia": "VARCHAR",
    "situacao_cadastral": "VARCHAR", "data_situacao": "VARCHAR",
    "motivo_situacao": "VARCHAR", "nome_cidade_exterior": "VARCHAR",
    "pais": "VARCHAR", "data_inicio_atividade": "VARCHAR",
    "cnae_fiscal_principal": "VARCHAR", "cnae_fiscal_secundario": "VARCHAR",
    "tipo_logradouro": "VARCHAR", "logradouro": "VARCHAR", "numero": "VARCHAR",
    "complemento": "VARCHAR", "bairro": "VARCHAR", "cep": "VARCHAR",
    "uf": "VARCHAR", "codigo_municipio": "VARCHAR", "municipio": "VARCHAR",
    "ddd_1": "VARCHAR", "telefone_1": "VARCHAR", "ddd_2": "VARCHAR",
    "telefone_2": "VARCHAR", "ddd_fax": "VARCHAR", "fax": "VARCHAR",
    "correio_eletronico": "VARCHAR", "situacao_especial": "VARCHAR",
    "data_situacao_especial": "VARCHAR",
}

EMP_COLS = {
    "cnpj_basico": "VARCHAR", "razao_social": "VARCHAR",
    "natureza_juridica": "VARCHAR", "qualificacao_responsavel": "VARCHAR",
    "capital_social": "VARCHAR", "porte": "VARCHAR", "ente_federativo": "VARCHAR",
}

# ─── UTILS ────────────────────────────────────────────────────────────────────


def limpar_cnpj(n: str) -> str:
    return re.sub(r"\D", "", n)


def fmt_cnpj(n: str) -> str:
    n = limpar_cnpj(n)
    return f"{n[:2]}.{n[2:5]}.{n[5:8]}/{n[8:12]}-{n[12:]}"


def parse_capital(val: Any) -> float:
    if not val:
        return 0.0
    s = str(val).strip()
    if not s or s == "0":
        return 0.0
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def fmt_bytes(n: int) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


def col_def_sql(cols: dict) -> str:
    items = ", ".join(f"'{k}': '{v}'" for k, v in cols.items())
    return "{" + items + "}"


# ─── FASE 1: PERFIL ──────────────────────────────────────────────────────────


def consultar_cnpj(cnpj_raw: str) -> dict:
    cnpj = limpar_cnpj(cnpj_raw)
    r = requests.get(OPENCNPJ_URL.format(cnpj), timeout=15)
    r.raise_for_status()
    return r.json()


def calcular_perfil(cnpjs: list[str]) -> dict:
    print(">> Consultando CNPJs via OpenCNPJ...")
    perfis = []
    for c in cnpjs:
        p = consultar_cnpj(c)
        perfis.append(p)
        time.sleep(0.05)

    capitals = [parse_capital(p.get("capital_social", "0")) for p in perfis]
    media = sum(capitals) / len(capitals)

    cnaes = [p.get("cnae_principal", "")[:2] for p in perfis if p.get("cnae_principal")]
    cnae_top = max(set(cnaes), key=cnaes.count) if cnaes else "46"

    perfil = {
        "empresas": [
            {
                "cnpj": limpar_cnpj(cnpjs[i]),
                "cnpj_fmt": fmt_cnpj(cnpjs[i]),
                "razao": p.get("razao_social", "?"),
                "capital": capitals[i],
                "cnae": p.get("cnae_principal", ""),
                "uf": p.get("uf", "?"),
                "cidade": p.get("municipio", "?"),
                "porte": p.get("porte_empresa", "?"),
            }
            for i, p in enumerate(perfis)
        ],
        "media_capital": media,
        "cnae_alvo": cnae_top,
        "cap_min": media * CAP_MIN_FATOR,
        "cap_max": media * CAP_MAX_FATOR,
    }

    print(f"   Capital social medio: R$ {media:,.2f}")
    print(f"   Faixa busca: R$ {perfil['cap_min']:,.2f} - R$ {perfil['cap_max']:,.2f}")
    print(f"   CNAE referencia: {cnae_top}")
    return perfil


# ─── FASE 2: DADOS ───────────────────────────────────────────────────────────


def _dl(url: str, dest: Path):
    tmp = dest.with_suffix(".tmp")
    r = requests.get(url, stream=True, timeout=(30, 300))
    r.raise_for_status()
    total = int(r.headers.get("content-length", 0))
    baixado = 0
    t0 = time.time()
    with open(tmp, "wb") as f:
        for chunk in r.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
                baixado += len(chunk)
    tmp.rename(dest)
    t = time.time() - t0
    vel = fmt_bytes(baixado / t) + "/s" if t > 0 else "?"
    return baixado, t, vel


def baixar_empresas(estab_inicio: float) -> Path:
    EMPRESAS_DIR.mkdir(parents=True, exist_ok=True)
    faltando = []
    for f in EMPRESAS_ZIPS:
        p = EMPRESAS_DIR / f
        if not p.exists() or p.stat().st_size == 0:
            faltando.append(f)
    if not faltando:
        return EMPRESAS_DIR

    print(f">> Baixando {len(faltando)} arquivos de empresas (~{fmt_bytes(526232879*10)})...")
    urls = [(urljoin(DADOS_URL, f"{LATEST}/{f}"), f) for f in faltando]

    ok = 0
    with ThreadPoolExecutor(max_workers=3) as pool:
        fut = {pool.submit(_dl, u, EMPRESAS_DIR / f): f for u, f in urls}
        for done in as_completed(fut):
            nome = fut[done]
            try:
                sz, t, vel = done.result()
                print(f"   OK {nome} ({fmt_bytes(sz)} em {t:.0f}s, {vel})")
                ok += 1
            except Exception as e:
                print(f"   FAIL {nome}: {e}")
    if ok:
        print(f"   Empresas concluido em {time.time()-estab_inicio:.0f}s")
    return EMPRESAS_DIR


def stream_estabelecimentos(num_arquivos: int = 10) -> Path:
    if ESTAB_CACHE.exists() and ESTAB_CACHE.stat().st_size > 0:
        print(">> Estabelecimentos PR/SC em cache.")
        return ESTAB_CACHE

    n = min(num_arquivos, 10)
    total_dados = 526232879 * n  # ~540MB each
    print(f">> Baixando e filtrando Estabelecimentos ({n}/{10} arquivos)...")
    print(f"   Dados brutos: ~{fmt_bytes(total_dados)}, armazenando apenas PR/SC")
    print("   (pressione Ctrl+C a qualquer momento, progresso e salvo)")
    print()

    ESTAB_CACHE.parent.mkdir(parents=True, exist_ok=True)
    inicio_total = time.time()
    total_linhas = 0

    with open(ESTAB_CACHE, "ab") as out:
        for i, arq_nome in enumerate(ESTAB_ZIPS[:n], 1):
            url = urljoin(DADOS_URL, f"{LATEST}/{arq_nome}")
            t0 = time.time()

            # Grep fields: CNAE (field 12) starts with 46-50. UF (field 20) = PR|SC
            cmd = (
                f"curl -s '{url}' "
                f"| funzip "
                f"| iconv -f ISO-8859-1 -t UTF-8//TRANSLIT "
                f"| LANG=C grep -E '^([^|]*\\|){{11}}(4[6-9]|50)' "
                f"| LANG=C grep -E '^([^|]*\\|){{19}}(PR|SC)\\|'"
            )
            proc = subprocess.Popen(
                cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                bufsize=65536
            )
            n_linhas = 0
            while True:
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                out.write(chunk)
                n_linhas += chunk.count(b"\n")
            proc.wait()
            t = time.time() - t0
            total_linhas += n_linhas
            acum = time.time() - inicio_total
            restante = (acum / i) * (n - i) if i < n else 0
            print(f"   [{i}/{n}] {arq_nome}: {n_linhas} linhas PR/SC, "
                  f"{t:.0f}s (restante ~{restante:.0f}s)")

    sz = ESTAB_CACHE.stat().st_size
    print(f"   Total: {total_linhas} linhas, {fmt_bytes(sz)}, "
          f"em {time.time()-inicio_total:.0f}s")
    return ESTAB_CACHE


# ─── FASE 3: DB ──────────────────────────────────────────────────────────────


def build_db(num_estab: int = 10):
    if DB_FILE.exists():
        return DB_FILE
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)

    print("\n>> Construindo banco DuckDB...")

    # Overlap: start Estabelecimentos streaming first, then Empresas in parallel
    estab_inicio = time.time()
    estab_file = stream_estabelecimentos(num_estab)
    empresas_dir = baixar_empresas(estab_inicio)

    con = duckdb.connect(str(DB_FILE))
    con.execute("SET threads=4")
    con.execute("SET memory_limit='2GB'")

    cnae_pat = "^(" + "|".join(CNAE_IMP) + ")"

    print("\n   Carregando estabelecimentos PR/SC...")
    n_estab = 0
    try:
        con.execute(f"""
            CREATE TABLE estabelecimentos AS
            SELECT * FROM read_csv(
                '{estab_file}',
                sep='|', header=false, quote='', strict_mode=false,
                columns={col_def_sql(ESTAB_COLS)},
                auto_detect=false, ignore_errors=true
            )
            WHERE situacao_cadastral = '{SIT_ATIVA}'
        """)
        n_estab = con.execute("SELECT COUNT(*) FROM estabelecimentos").fetchone()[0]
        print(f"      Estabelecimentos ativos PR/SC: {n_estab}")
    except Exception as e:
        print(f"      Erro ao carregar estabelecimentos: {e}")
        print("      (pode ser encoding - tente rebuildar com --shallow)")
    if n_estab == 0:
        con.close()
        DB_FILE.unlink(missing_ok=True)
        return None

    if cnae_pat:
        con.execute(f"""
            DELETE FROM estabelecimentos
            WHERE NOT regexp_matches(cnae_fiscal_principal, '{cnae_pat}')
        """)
        n_imp = con.execute("SELECT COUNT(*) FROM estabelecimentos").fetchone()[0]
        print(f"      Importadores (CNAE {','.join(CNAE_IMP)}): {n_imp}")

    con.execute("CREATE INDEX idx_est_cnpj ON estabelecimentos(cnpj_basico)")

    print("   Carregando empresas...")
    emp_zips = sorted(empresas_dir.glob("Empresas*.zip"))
    emp_paths = ", ".join(f"'{e}'" for e in emp_zips)
    con.execute(f"""
        CREATE TABLE empresas AS
        SELECT cnpj_basico, razao_social, capital_social, porte
        FROM read_csv(
            [{emp_paths}],
            sep='|', header=false, quote='', strict_mode=false,
            columns={col_def_sql(EMP_COLS)},
            auto_detect=false, ignore_errors=true
        )
    """)
    n_emp = con.execute("SELECT COUNT(*) FROM empresas").fetchone()[0]
    print(f"      Empresas: {n_emp}")
    con.execute("CREATE INDEX idx_emp_cnpj ON empresas(cnpj_basico)")

    con.execute("ANALYZE")
    con.close()
    print("   Banco pronto!")
    return DB_FILE


# ─── FASE 4: BUSCA ───────────────────────────────────────────────────────────


def buscar(perfil: dict) -> list[dict]:
    print(">> Buscando importadores similares em PR/SC...")
    con = duckdb.connect(str(DB_FILE), read_only=True)

    cap_min = perfil["cap_min"]
    cap_max = perfil["cap_max"]
    prefixos = list(set(CNAE_IMP + [perfil["cnae_alvo"]]))
    cnae_pat = "(" + "|".join(prefixos) + ")"

    q = f"""
        SELECT
            e.cnpj_basico || e.cnpj_ordem || e.cnpj_dv AS cnpj_num,
            COALESCE(e.municipio, 'N/D') AS municipio,
            e.cnae_fiscal_principal,
            COALESCE(emp.razao_social, 'N/D') AS razao,
            emp.capital_social,
            COALESCE(emp.porte, 'N/D') AS porte
        FROM estabelecimentos e
        LEFT JOIN empresas emp ON e.cnpj_basico = emp.cnpj_basico
        WHERE e.uf IN ('PR', 'SC')
          AND regexp_matches(e.cnae_fiscal_principal, '{cnae_pat}')
    """

    try:
        rows = con.execute(q).fetchall()
    except Exception as e:
        print(f"   Erro SQL: {e}")
        rows = []
    con.close()

    parsed = []
    for r in rows:
        cap = parse_capital(r[4])
        if cap_min <= cap <= cap_max:
            parsed.append({
                "cnpj": r[0].zfill(14),
                "cnpj_fmt": fmt_cnpj(r[0].zfill(14)),
                "razao": r[3],
                "uf": "PR/SC",
                "cidade": r[1],
                "cnae": r[2],
                "capital": cap,
                "porte": r[5],
            })

    parsed.sort(key=lambda x: x["capital"], reverse=True)
    return parsed[:LIMITE]


# ─── EXIBIR ───────────────────────────────────────────────────────────────────


def exibir(lista: list[dict], titulo: str):
    print(f"\n{'='*70}")
    print(f"  {titulo}")
    print(f"{'='*70}")
    for i, e in enumerate(lista, 1):
        cap = f"R$ {e['capital']:,.2f}" if e.get("capital") else "N/D"
        print(f"\n{i}. {e.get('cnpj_fmt', e.get('cnpj', '?'))}")
        print(f"   Razao: {e['razao']}")
        print(f"   Local: {e.get('cidade', '?')}/{e['uf']}")
        print(f"   CNAE:  {e.get('cnae', '?')}")
        print(f"   Cap:   {cap}")
        if e.get("porte"):
            print(f"   Porte: {e['porte']}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────


def main():
    args = sys.argv[1:]
    profile_only = "--profile" in args
    shallow = 10
    db_url = None

    if profile_only:
        args.remove("--profile")
    if "--shallow" in args:
        idx = args.index("--shallow")
        args.pop(idx)
        shallow = int(args.pop(idx)) if idx < len(args) and args[idx].isdigit() else 3
    for a in args:
        if a.startswith("--db-url="):
            db_url = a.split("=", 1)[1]
            args.remove(a)
            break

    if len(args) != 3:
        print(__doc__)
        sys.exit(1)

    cnpjs = args[0:3]
    inicio = time.time()

    # ── Phase 1: Profile (instant) ──
    perfil = calcular_perfil(cnpjs)
    print()
    exibir(perfil["empresas"], "EMPRESAS DE REFERENCIA")

    if not profile_only:
        built = False
        if db_url:
            print(f"\n>> Baixando DuckDB de {db_url}...")
            r = requests.get(db_url, stream=True, timeout=30)
            r.raise_for_status()
            with open(DB_FILE, "wb") as f:
                for c in r.iter_content(65536):
                    if c:
                        f.write(c)
            built = True
            print("   OK")

        if not built and not DB_FILE.exists():
            print("\n>> ATENCAO: primeira execucao requer download de dados publicos")
            print(f"   Usando modo --shallow {shallow} ({shallow}/10 arquivos)")
            print("   (para resposta completa, remova --shallow)")
            print("   (para pular, use --profile)")
            print()
        try:
            if not built:
                build_db(num_estab=shallow)
            if DB_FILE.exists():
                resultados = buscar(perfil)
                if resultados:
                    exibir(resultados, f"IMPORTADORES SIMILARES PR/SC ({len(resultados)})")
                else:
                    print("\nNenhum resultado. Tente mais arquivos (sem --shallow) ou")
                    print("ajuste CNAE_IMP/faixas de capital no script.")
        except KeyboardInterrupt:
            print("\n\nInterrompido. Progresso salvo - proxima execucao continua de onde parou.")

    print(f"\nTempo total: {time.time() - inicio:.0f}s")


if __name__ == "__main__":
    main()
