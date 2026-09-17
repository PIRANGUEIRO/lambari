#!/usr/bin/env python3
"""
Site Contact Extractor v3 — varredura paralela com sitemap + prioridade inteligente

Uso:
    python site_contacts.py https://exemplo.com.br
    python site_contacts.py exemplo.com.br --json
    python site_contacts.py exemplo.com.br --csv > contatos.csv
"""

import os, sys, re, json, ssl, urllib.request, urllib.error, html as html_mod
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from collections import deque
from dataclasses import dataclass, field, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock


# ─── CONFIG ───────────────────────────────────
MAX_PAGINAS = 50
THREADS = 5
TIMEOUT = 6
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ─── PADRÕES ──────────────────────────────────
RE_EMAIL = re.compile(r'[a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}')
RE_TEL = re.compile(r'(?:\(?\d{2}\)?\s?)?(?:9?\d{4}-\d{4}|\d{4,5}-\d{4})')
RE_TEL_LIMPO = re.compile(r'(?<!\d)(?:[1-9]\d{9}|[1-9]\d{10})(?!\d)')  # 10-11 dígitos sem formatação
RE_NOME = re.compile(r'(?:[A-ZÀ-Ú][a-zà-ú]{2,}(?:\s+[A-ZÀ-Ú][a-zà-ú]{2,}){1,4})')
RE_CARGO = re.compile(r'(?:CEO|CTO|CFO|COO|Diretor|Diretora|Gerente|Coordenador|Analista|Founder|Sócio|Presidente|Manager|Coordinator|Analyst|Developer|Consultor|Supervisor|Líder|Founder|Partner|VP|Head|Lead|Owner|Superintendente|Assessor|Assistente|Encarregado|Representante|Secretário|Tesoureiro|Controller|Suporte|Especialista)', re.I)

# ─── CONHECIMENTO DE NOMES BRASILEIROS ────────
PRIMEIROS_NOMES = {
    "João", "Maria", "José", "Ana", "Pedro", "Paulo", "Carlos", "Antônio",
    "Francisco", "Luiz", "Miguel", "Lucas", "Gabriel", "Rafael", "Felipe",
    "Fernando", "Roberto", "Eduardo", "Marcelo", "Alexandre", "Ricardo",
    "Leonardo", "André", "Diego", "Bruno", "Daniel", "Gustavo", "Marcos",
    "Ronaldo", "Julio", "Thiago", "Rodrigo", "Luciano", "Márcio", "Leandro",
    "Sérgio", "Fabiano", "Vinicius", "Renato", "Cristiano", "Rogério",
    "Maurício", "Adriano", "Jorge", "Cláudio", "Valdir", "Osvaldo",
    "Alessandro", "Edson", "Elias", "Ivan", "Leonel", "Mauro", "Nelson",
    "Otávio", "Vítor", "Wagner", "Alex", "Alan", "Adilson", "Alberto",
    "Augusto", "César", "Ciro", "Davi", "Douglas", "Emerson", "Erick",
    "Fabio", "Fábio", "Flávio", "Heitor", "Hélio", "Hugo", "Igor",
    "Júlio", "Luis", "Márcio", "Matheus", "Milton", "Murilo", "Orlando",
    "Oscar", "Pablo", "Raul", "Reinaldo", "Saulo", "Sidney", "Tales",
    "Túlio", "Ulisses", "Valter", "Vanderlei", "Wesley", "William",
    "Yuri", "Alice", "Sofia", "Laura", "Beatriz", "Isabela", "Manuela",
    "Júlia", "Helena", "Valentina", "Lara", "Lívia", "Marina", "Camila",
    "Larissa", "Letícia", "Amanda", "Bruna", "Carla", "Cynthia",
    "Daniela", "Débora", "Eliane", "Elisa", "Erika", "Fabiana",
    "Fernanda", "Gabriela", "Giovana", "Heloísa", "Ingrid", "Irene",
    "Jaqueline", "Jéssica", "Joana", "Juliana", "Kátia", "Luciana",
    "Luiza", "Márcia", "Michele", "Monique", "Nathalia", "Patrícia",
    "Priscila", "Raquel", "Renata", "Sabrina", "Sandra", "Sara",
    "Silvia", "Simone", "Suellen", "Tatiane", "Tereza", "Vanessa",
    "Viviane", "Adriana", "Aline", "Bianca", "Carolina", "Cristina",
    "Daiane", "Denise", "Diana", "Elaine", "Elen", "Gisele",
    "Graziele", "Isabel", "Janaina", "Karen", "Lilian", "Lorena",
    "Luciene", "Michelli", "Nayara", "Neide", "Pamela", "Regina",
    "Rita", "Rute", "Sueli", "Tânia", "Valéria", "Vera", "William", "Yasmin",
}

SOBRENOMES_COMUNS = {
    "Silva", "Santos", "Oliveira", "Souza", "Lima", "Costa", "Pereira",
    "Almeida", "Nascimento", "Ferreira", "Rodrigues", "Martins", "Jesus",
    "Carvalho", "Gomes", "Ribeiro", "Araújo", "Barbosa", "Rocha", "Moreira",
    "Alves", "Cardoso", "Teixeira", "Cavalcanti", "Dias", "Castro", "Campos",
    "Melo", "Cunha", "Mendes", "Vieira", "Monteiro", "Miranda", "Freitas",
    "Machado", "Pinto", "Correia", "Neves", "Coelho", "Lopes", "Cruz",
    "Pires", "Moraes", "Batista", "Barros", "Nunes", "Viana", "Leite",
    "Camargo", "Aragão", "Farias", "Maia", "Medeiros", "Gonçalves",
    "Marques", "Fernandes", "Andrade", "Borges", "Azevedo", "Xavier",
    "Tavares", "Bastos", "Figueiredo", "Sales", "Assis", "Fonseca",
    "Ardigó", "Milito", "Colin", "Parigot", "Viriato",
}

CIDADES_BR = {
    "belo horizonte", "são paulo", "rio de janeiro", "curitiba",
    "porto alegre", "salvador", "brasília", "fortaleza", "recife",
    "florianópolis", "santos", "campinas", "guarulhos", "são bernardo",
    "santo andré", "ribeirão preto", "uberlândia", "contagem", "betim",
    "nova lima", "belém", "manaus", "goiânia", "vitória", "niterói",
    "duque de caxias", "são josé", "são caetano", "mogi", "osasco",
    "barueri", "jundiaí", "sorocaba", "taubaté", "piracicaba",
    "londrina", "maringá", "cascavel", "blumenau", "joinville",
    "criciúma", "chapecó", "caxias do sul", "pelotas", "rio grande",
    "campo grande", "cuiabá", "teresina", "são luís", "natal",
    "joão pessoa", "maceió", "aracaju", "macapá", "palmas",
    "boa vista", "rio branco", "porto velho", "são gonçalo",
    "nova iguaçu", "cabo frio", "petrópolis", "teresópolis",
    "angra dos reis", "resende", "volta redonda", "barra mansa",
    "campos", "macaé", "arraial do cabo", "búzios", "uberaba",
    "divinópolis", "sete lagoas", "ipatinga", "poços de caldas",
    "varginha", "ouro preto", "mariana", "juiz de fora",
    "governador valadares", "teófilo otoni", "montes claros",
    "pouso alegre", "itajubá", "alfenas", "passos", "votuporanga",
    "são josé do rio preto", "são josé dos campos", "são josé dos pinhais",
    "santa maria", "novo hamburgo", "canoas", "gravataí",
    "viamão", "alvorada", "sapucaia do sul", "esteio", "são leopoldo",
    "cachoeirinha", "guaíba", "charqueadas", "triunfo", "montenegro",
    "portão", "estância velha", "ivoti", "dois irmãos", "novo xingu",
    "santa rosa", "passo fundo", "erechim", "bagé", "uruguaiana",
    "santana do livramento", "itajaí", "balneário camboriú", "itapema",
    "porto belo", "bombinhas", "navegantes", "araquari",
    "são francisco do sul", "laguna", "tubarão", "palhoça",
    "biguaçu", "santo amaro da imperatriz", "são josé", "alfredo wagner",
}

ESTADOS_BR = {
    "acre", "alagoas", "amapá", "amazonas", "bahia", "ceará",
    "distrito federal", "espírito santo", "goiás", "maranhão",
    "mato grosso", "mato grosso do sul", "minas gerais", "pará",
    "paraíba", "paraná", "pernambuco", "piauí", "rio de janeiro",
    "rio grande do norte", "rio grande do sul", "rondônia", "roraima",
    "santa catarina", "são paulo", "sergipe", "tocantins",
}

PAISES = {
    "brasil", "argentina", "chile", "uruguai", "paraguai", "bolívia",
    "peru", "colômbia", "venezuela", "equador", "guiana", "suriname",
    "áfrica do sul", "angola", "moçambique", "portugal", "espanha",
    "frança", "inglaterra", "reino unido", "alemanha", "itália",
    "holanda", "países baixos", "bélgica", "suíça", "suécia",
    "noruega", "dinamarca", "finlândia", "polônia", "tcheca",
    "hungria", "romênia", "bulgária", "grécia", "turquia",
    "rússia", "ucrânia", "china", "japão", "coreia", "índia",
    "indonésia", "malásia", "singapura", "tailândia", "vietnã",
    "filipinas", "austrália", "nova zelândia", "egito", "marrocos",
    "nigéria", "gana", "argélia", "tunísia", "emirados árabes",
    "arábia saudita", "catar", "kuwait", "omã", "barein",
    "méxico", "canadá", "estados unidos", "cuba", "porto rico",
    "república dominicana", "panamá", "costa rica", "guatemala",
    "honduras", "el salvador", "nicarágua",
}

BAIRROS_SP = {
    "alphaville", "vila olímpia", "itaim bibi", "jardins", "moema",
    "vila mariana", "pinheiros", "butantã", "morumbi", "santo amaro",
    "bela vista", "consolação", "cerqueira césar", "perdizes",
    "pompéia", "lapa", "barra funda", "vila leopoldina",
    "tatuapé", "mooca", "ipiranga", "saúde", "jabaquara",
    "santo andré", "são bernardo", "são caetano", "diadema",
    "guarulhos", "osasco", "taboão", "embu", "cotia", "carapicuíba",
}

BAIRROS_RJ = {
    "copacabana", "ipanema", "leblon", "barra da tijuca", "recreio",
    "botafogo", "flamengo", "laranjeiras", "cosme velho", "lagoa",
    "gávea", "são conrado", "vidigal", "rocinha", "centro",
    "cidade nova", "santo cristo", "gamboa", "saúde", "tijuca",
    "vila isabel", "andarai", "grajaú", "méier", "engenho novo",
    "cascadura", "madureira", "bangu", "realengo", "campo grande",
    "santa cruz", "ilha do governador", "paquetá", "niterói",
    "maricá", "iguaçu", "caxias", "nova iguaçu", "belford roxo",
    "são gonçalo", "itanhangá", "jacarepaguá", "taquara", "curicica",
}

CIDADES_EXTERIOR = {
    "new york", "los angeles", "chicago", "miami", "orlando",
    "london", "paris", "berlin", "madrid", "barcelona", "lisboa",
    "porto", "roma", "milão", "veneza", "amsterdã", "bruxelas",
    "zurique", "genebra", "viena", "budapeste", "praga",
    "varsóvia", "estocolmo", "oslo", "copenhague", "helsinki",
    "dublin", "edimburgo", "moscou", "são petersburgo",
    "xangai", "pequim", "hong kong", "toquio", "osaka",
    "seul", "bangkok", "cidade do méxico", "bogotá",
    "lima", "santiago", "buenos aires", "montevidéu", "assunção",
    "cairo", "dubai", "doha", "istambul", "sydney", "melbourne",
    "cidade do cabo", "luanda", "maputo", "são tomé",
    "rotterdam", "hamburgo", "los angeles", "valparaíso",
    "callao", "cartagena", "colón", "manzanillo", "veracruz",
}

LUGARES = CIDADES_BR | ESTADOS_BR | PAISES | BAIRROS_SP | BAIRROS_RJ | CIDADES_EXTERIOR
# Remove sobreposições de nomes próprios (ex: "João Pessoa" é cidade mas João é nome)
LUGARES_SEM_NOMES = {
    x for x in LUGARES
    if not any(x.startswith(n.lower()) for n in PRIMEIROS_NOMES)
}

NAVEGACAO = {
    "próximo", "próxima", "anterior", "voltar", "anterior",
    "prev", "next", "anterior", "voltar", "início", "volta",
    "primeira", "segunda", "terceira", "anterior",
    "mais antigos", "mais recentes", "posts recentes",
    "posts", "página", "página anterior", "página seguinte",
    "primeira página", "última página", "resultados",
    "exibindo", "mostrando", "filtrar", "ordenar",
    "carregar mais", "ver todos", "selecionar",
    "anterior entenda", "anterior análise", "anterior saiba",
    "anterior conheça", "anterior férias", "anterior cenário",
    "anterior golden", "anterior manifestações", "anterior maio",
    "anterior exportação", "anterior importação",
    "próximo conheça", "próximo entenda", "próximo cenário",
    "próximo saiba", "próximo certificação", "próximo análise",
    "próximo férias", "próximo exportação", "próximo golden",
    "próximo manifestações", "próximo maio",
    "primeiro andar", "segundo andar", "terreo", "subsolo",
}

PRIMEIRAS_PALAVRAS_BLOQUEADAS = {
    "segundo", "primeiro", "terceiro", "quarto", "quinto",
    "leste", "oeste", "norte", "sul", "sudeste", "nordeste",
    "sudoeste", "noroeste", "centro-oeste",
}

JARGAO = {
    "lead time", "peak season", "blank sailing", "blank sailings",
    "general rate increase", "general rate increases",
    "pure car carrier", "open tops", "high cube", "hub ports",
    "coast europe express", "ferries são", "golden week",
    "black friday", "trading company", "papai noel",
    "cct", "oea", "radar", "drawback", "duimp", "siscomex",
    "bonded warehouse", "cross docking", "ro ro",
    "demurrage", "detention", "free time", "free days",
    "container", "containers", "reefer", "flat rack",
    "break bulk", "project cargo", "ltl", "ftl",
    "deadline", "lead",
    "comércio exterior", "comércio internacional",
    "logistics", "shipping", "forwarder", "freight",
    "importação", "exportação", "despacho aduaneiro",
    "receita federal", "polícia rodoviária federal",
    "agência nacional", "companhia nacional",
    "organização mundial", "empresa brasileira",
    "pesquisa agropecuária", "desenvolvimento humano",
    "indústria química", "indústria farmacêutica",
    "indústria têxtil", "indústria alimentícia",
    "principais usos", "principais continentes",
    "outros mercados", "eventos culturais",
    "jogos olímpicos", "ano novo chinês",
    "feriado chinês", "oportunidades",
    "boas práticas", "contêineres esses",
    "navegantes devido", "lucros imposto",
    "transportes", "transportador rodoviário",
    "operações aéreas", "aeroportos restrições",
    "perecíveis durante", "festivais muitos",
    "transporte nessas", "china próximo",
    "europa próximo", "ásia próximo", "área próximo",
    "mercado próximo", "global próximo",
    "prev anterior", "prev anterior entenda",
    "prev anterior análise", "prev anterior saiba",
    "prev anterior conheça", "prev anterior férias",
    "prev anterior cenário", "prev anterior golden",
    "prev anterior manifestações", "prev anterior maio",
    "prev anterior exportação", "prev anterior importação",
    "próximas semanas", "mercado áfrica", "área mercado",
    "sobreane", "work", "premium", "trade",
    "sobre segunda", "segurança nossa",
    "costa leste", "costa oeste", "costa norte", "costa sul",
}

TAGS_PULAR = {"style", "script", "noscript", "iframe", "svg", "canvas"}

SOCIAL_PATTERNS = {
    "linkedin": [
        r'https?://(?:www\.|br\.)?linkedin\.com/company/[\w.-]+',
        r'https?://(?:www\.|br\.)?linkedin\.com/in/[\w.-]+',
    ],
    "instagram": [r'https?://(?:www\.)?instagram\.com/[\w.]+'],
    "facebook": [r'https?://(?:www\.)?(?:facebook|fb)\.com/[\w.]+'],
    "twitter": [r'https?://(?:www\.)?(?:twitter|x)\.com/[\w_]+'],
    "youtube": [r'https?://(?:www\.)?youtube\.com/@?[\w-]+', r'https?://(?:www\.)?youtube\.com/channel/[\w-]+'],
    "tiktok": [r'https?://(?:www\.)?tiktok\.com/@[\w.]+'],
    "whatsapp": [r'https?://(?:api\.)?whatsapp\.com/send/?\?phone=(\d+)', r'https?://wa\.(?:me|link)/(\d+)'],
    "telegram": [r'https?://(?:t\.me|telegram\.me)/([\w_]+)'],
}

# URLs mais prováveis de ter contato — visitamos primeiro
CAMINHOS_PRIORITARIOS = [
    "/contato", "/contact", "/fale-conosco", "/faleconosco",
    "/sobre", "/sobre-nos", "/sobre-nos", "/quem-somos",
    "/about", "/about-us", "/who-we-are",
    "/equipe", "/team", "/nosso-time", "/time",
    "/servicos", "/services",
    "/trabalhe-conosco", "/trabalheconosco", "/careers", "/jobs",
    "/parceiros", "/partners",
    "/blog", "/novidades", "/news",
    "/sac", "/ouvidoria",
    "/politica-de-privacidade", "/privacidade", "/privacy",
    "/termos-de-uso", "/termos",
    "/imprensa", "/press", "/newsroom",
]

CAMINHOS_SECUNDARIOS = [
    "/", "/index", "/home", "/inicio",
    "/produtos", "/products",
    "/solucoes", "/solutions",
    "/portfolio", "/cases",
    "/faq", "/perguntas-frequentes",
    "/depoimentos", "/testimonials",
    "/galeria", "/gallery",
    "/eventos", "/events",
    "/cursos", "/courses",
    "/representantes", "/revendedores",
    "/seja-parceiro", "/seja-um-parceiro",
    "/indicacao", "/indique",
    "/afiliados", "/affiliates",
    "/app", "/download",
    "/central-de-ajuda", "/ajuda", "/help",
    "/mapa-do-site", "/sitemap",
]


# ─── UTILITÁRIOS ──────────────────────────────
def fetch(url: str, timeout: int = TIMEOUT) -> str | None:
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers=HEADERS)
        return urllib.request.urlopen(req, timeout=timeout, context=ctx).read().decode("utf-8", errors="replace")
    except Exception:
        return None


def normalizar(url: str, base: str) -> str | None:
    try:
        full = urljoin(base, url)
        p = urlparse(full)
        if p.scheme not in ("http", "https"):
            return None
        return f"{p.scheme}://{p.netloc}{p.path}".rstrip("/")
    except Exception:
        return None


def mesmo_dominio(url: str, dominio: str) -> bool:
    return dominio in urlparse(url).netloc.lower()


def ext_valida(path: str) -> bool:
    e = Path(path).suffix.lower()
    return e in ("", ".html", ".htm", ".php", ".asp", ".aspx", ".jsp", ".cfm", ".shtml")


def decodificar_html_entities(texto: str) -> str:
    return html_mod.unescape(texto)


def parece_data(num: str) -> bool:
    """8 dígitos que parecem DDMMYYYY ou MMDDYYYY — não é telefone."""
    if len(num) != 8:
        return False
    try:
        d, m = int(num[:2]), int(num[2:4])
        return (1 <= d <= 31 and 1 <= m <= 12) or (1 <= m <= 31 and 1 <= d <= 12)
    except ValueError:
        return False


def parece_nome_pessoa(nome: str) -> bool:
    nome_lower = nome.lower().strip()
    palavras = nome_lower.split()
    if len(palavras) < 2:
        return False
    primeiro = palavras[0]

    if not primeiro:
        return False

    if primeiro in PRIMEIRAS_PALAVRAS_BLOQUEADAS:
        return False
    if primeiro in NAVEGACAO:
        return False
    if nome_lower in NAVEGACAO:
        return False
    for n in NAVEGACAO:
        if n in nome_lower:
            return False
    for j in JARGAO:
        if j in nome_lower:
            return False
    for l in LUGARES_SEM_NOMES:
        if l in nome_lower:
            return False
    if any(nome_lower.endswith(p) for p in (" sp", " rj", " mg", " rs", " pr", " sc", " ba", " pe", " ce", " df", " es", " go", " bh", " ms", " mt", " pa", " ma", " pi", " rn", " pb", " al", " se", " ro", " ac", " am", " rr", " ap", " to")):
        return False
    if any(nome_lower.startswith(p) for p in ("rua", "av.", "avenida", "alameda", "travessa", "praça", "praca", "rodovia", "estrada", "edifício", "edificio", "largo", "beco", "viela")):
        return False
    if re.search(r'\b(?:sala|apto|ap|andar|bloco|torre|lote|quadra|loja)\s+\d+', nome_lower):
        return False

    # Nome deve parecer nome de pessoa: primeiro nome conhecido OU sobrenome conhecido
    primeiro_cap = palavras[0].capitalize()
    tem_nome = primeiro_cap in PRIMEIROS_NOMES
    tem_sobrenome = any(p.capitalize() in SOBRENOMES_COMUNS for p in palavras)

    if tem_nome and tem_sobrenome:
        return True
    if tem_nome and len(palavras) >= 2:
        return True
    if tem_sobrenome and len(palavras) >= 2 and re.search(r'[A-ZÀ-Ú][a-zà-ú]{2,}\s+[A-ZÀ-Ú]', nome):
        return True

    return False


# ─── PARSER SITEMAP ───────────────────────────
def parse_sitemap(xml: str) -> list[str]:
    urls = []
    for m in re.finditer(r'<loc>(.*?)</loc>', xml, re.I):
        u = m.group(1).strip()
        if u:
            urls.append(u)
    return urls


# ─── CNPJ ─────────────────────────────────────
def consultar_cnpj(cnpj: str) -> dict | None:
    """Consulta CNPJ na ReceitaWS (gratuita, sem chave)."""
    limpo = re.sub(r'\D', '', cnpj)
    if len(limpo) != 14:
        return None
    # Mock API — antes: https://api.exemplo.com/v1/cnpj/
    base = os.getenv("CNPJ_API_URL", "https://api.exemplo.com/cnpj/{}").replace("{}", "")
    url = f"{base.rstrip('/')}/{limpo}"
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={"User-Agent": HEADERS["User-Agent"]})
        resp = urllib.request.urlopen(req, timeout=8, context=ctx)
        return json.loads(resp.read().decode())
    except Exception:
        return None


def extrair_cnpjs(texto: str) -> list[str]:
    return list(set(re.findall(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', texto)))


# ─── PARSER HTML ──────────────────────────────
class PageParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.links: set[str] = set()
        self.emails: set[str] = set()
        self.social: dict[str, set[str]] = {k: set() for k in SOCIAL_PATTERNS}
        self.phones: set[str] = set()
        self.nomes: set[str] = set()
        self.cargos: list[tuple[str, str]] = []
        self.texto: list[str] = []
        self.cnpjs: list[str] = []
        self._pular = 0

    def handle_starttag(self, tag, attrs):
        if tag in TAGS_PULAR:
            self._pular += 1
            return
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            href = a["href"]
            self.links.add(urljoin(self.base_url, href))
            if href.startswith("mailto:"):
                addr = urllib.parse.unquote(href[7:]).split("?")[0]
                self.emails.add(addr.lower())
            if href.startswith("tel:"):
                num = re.sub(r'\D', '', href[4:])
                if len(num) >= 8 and not parece_data(num):
                    self.phones.add(num)
        if tag == "meta":
            name = (a.get("name") or a.get("property") or "").lower()
            content = a.get("content", "")
            if name in ("author", "article:author") and "@" in content:
                self.emails.add(content.lower())
            if name in ("description", "og:description", "twitter:description"):
                self._extrair(content)

    def handle_endtag(self, tag):
        if tag in TAGS_PULAR:
            self._pular -= 1

    def handle_data(self, data):
        if not self._pular and len(data.strip()) > 3:
            self.texto.append(data.strip())

    def _extrair(self, texto: str):
        texto = decodificar_html_entities(texto)
        for e in RE_EMAIL.findall(texto):
            self.emails.add(e.lower())
        for p in RE_TEL.findall(texto):
            limpo = re.sub(r'\D', '', p)
            if limpo:
                self.phones.add(limpo)
        for p in RE_TEL_LIMPO.findall(texto):
            if not parece_data(p) and len(p) != 14:
                self.phones.add(p)
        for c in extrair_cnpjs(texto):
            self.cnpjs.append(c)
        for n in RE_NOME.findall(texto):
            if len(n.split()) >= 2 and parece_nome_pessoa(n):
                self.nomes.add(n.strip())

    def finalizar(self):
        texto = decodificar_html_entities(" ".join(self.texto))
        self._extrair(texto)

        for rede, patterns in SOCIAL_PATTERNS.items():
            for pat in patterns:
                for m in re.finditer(pat, texto):
                    self.social[rede].add(m.group(0))
                    break

        linhas = "\n".join(self.texto)
        for m in RE_CARGO.finditer(linhas):
            cargo = m.group(0)
            ctx = linhas[max(0, m.start() - 40):m.start()].strip()
            for n in RE_NOME.findall(ctx):
                if len(n.split()) >= 2 and parece_nome_pessoa(n):
                    self.cargos.append((cargo, n.strip()))


# ─── RESULTADO ─────────────────────────────────
@dataclass
class Resultado:
    url: str = ""
    dominio: str = ""
    paginas_visitadas: int = 0
    emails: list[str] = field(default_factory=list)
    telefones: list[str] = field(default_factory=list)
    pessoas: list[dict] = field(default_factory=list)
    cnpjs: list[str] = field(default_factory=list)
    cnpj_dados: dict | None = None
    linkedin_empresa: str | None = None
    linkedin_pessoas: list[str] = field(default_factory=list)
    instagram: list[str] = field(default_factory=list)
    facebook: list[str] = field(default_factory=list)
    twitter: list[str] = field(default_factory=list)
    youtube: list[str] = field(default_factory=list)
    tiktok: list[str] = field(default_factory=list)
    whatsapp: list[str] = field(default_factory=list)
    telegram: list[str] = field(default_factory=list)
    outras_redes: dict = field(default_factory=dict)
    paginas: list[str] = field(default_factory=list)
    sitemap_usado: bool = False


# ─── CRAWLER PRINCIPAL ────────────────────────
def site_contacts(url_inicial: str) -> Resultado:
    r = Resultado()

    if not url_inicial.startswith("http"):
        url_inicial = "https://" + url_inicial
    r.url = url_inicial.rstrip("/")
    dominio = urlparse(r.url).netloc.lower()
    if dominio.startswith("www."):
        dominio = dominio[4:]
    r.dominio = dominio
    base = f"https://{dominio}" if not dominio.startswith("www.") else f"https://www.{dominio}"

    # 1. Tenta sitemap.xml
    sitemap_urls: list[str] = []
    for url_tentativa in (f"{base}/sitemap.xml", f"{base}/sitemap_index.xml", f"{base}/sitemap"):
        xml = fetch(url_tentativa, timeout=4)
        if xml:
            encontradas = parse_sitemap(xml)
            if encontradas:
                r.sitemap_usado = True
                for su in encontradas:
                    if "sitemap" in su.lower() and su != url_tentativa:
                        sub = fetch(su, timeout=4)
                        if sub:
                            sitemap_urls.extend(parse_sitemap(sub))
                    else:
                        sitemap_urls.append(su)
                if sitemap_urls:
                    break
        if sitemap_urls:
            break

    # 2. Monta lista de URLs pra visitar
    all_urls: list[str] = []

    if sitemap_urls:
        for u in sitemap_urls:
            if mesmo_dominio(u, dominio) and ext_valida(urlparse(u).path):
                all_urls.append(u)
        palavras_contato = {"contato", "contact", "sobre", "about", "equipe", "team",
                            "fale", "quem-somos", "trabalhe", "career", "parceiro"}
        fila_prioritaria: list[str] = []
        fila_normal: list[str] = []
        for u in all_urls:
            path = urlparse(u).path.lower()
            if any(p in path for p in palavras_contato):
                fila_prioritaria.append(u)
            else:
                fila_normal.append(u)
        all_urls = fila_prioritaria + fila_normal
    else:
        for path in CAMINHOS_PRIORITARIOS:
            all_urls.append(f"{base}{path}")

    if r.url not in all_urls:
        all_urls.append(r.url)

    all_urls = all_urls[:MAX_PAGINAS]

    # 3. Crawl paralelo
    lock = Lock()
    emails: set[str] = set()
    phones: set[str] = set()
    nomes: dict[str, str] = {}
    social: dict[str, set[str]] = {}
    cnpjs: list[str] = []
    paginas: list[str] = []
    visited: set[str] = set()

    def crawl(url: str) -> None:
        nonlocal visited
        if url in visited:
            return
        with lock:
            if url in visited:
                return
            visited.add(url)

        print(f"  ↳ {url}", file=sys.stderr)
        html = fetch(url, timeout=TIMEOUT)
        if not html:
            return

        parser = PageParser(url)
        try:
            parser.feed(html)
        except Exception:
            return
        parser.finalizar()

        with lock:
            emails.update(parser.emails)
            phones.update(parser.phones)
            for nome in parser.nomes:
                cargo = ""
                for c, n in parser.cargos:
                    if n in nome or nome in n:
                        cargo = c
                        break
                if nome not in nomes:
                    nomes[nome] = cargo
            for rede, urls in parser.social.items():
                if rede not in social:
                    social[rede] = set()
                social[rede].update(urls)
            cnpjs.extend(parser.cnpjs)
            paginas.append(url)

    with ThreadPoolExecutor(max_workers=THREADS) as exec:
        futuros = {exec.submit(crawl, u): u for u in all_urls}
        for _ in as_completed(futuros):
            pass

    # 4. Preenche resultado
    r.paginas_visitadas = len(visited)
    r.emails = sorted(emails)
    r.telefones = sorted(phones)
    r.pessoas = [{"nome": n, "cargo": c} for n, c in nomes.items()]
    r.paginas = sorted(paginas)
    r.cnpjs = sorted(set(cnpjs))

    # Se achou CNPJ, consulta
    if r.cnpjs:
        r.cnpj_dados = consultar_cnpj(r.cnpjs[0])

    for rede, urls in social.items():
        lista = list(urls)
        if rede == "linkedin":
            for u in lista:
                if "/company/" in u:
                    r.linkedin_empresa = u
                elif "/in/" in u:
                    r.linkedin_pessoas.append(u)
        elif rede == "instagram":  r.instagram = lista
        elif rede == "facebook":   r.facebook = lista
        elif rede == "twitter":    r.twitter = lista
        elif rede == "youtube":    r.youtube = lista
        elif rede == "tiktok":     r.tiktok = lista
        elif rede == "whatsapp":   r.whatsapp = lista
        elif rede == "telegram":   r.telegram = lista
        else: r.outras_redes[rede] = lista

    return r


# ─── OUTPUT ───────────────────────────────────
def fmt(r: Resultado) -> str:
    L = [f"┌─ {r.url}"]
    L.append(f"│ 📄 Páginas: {r.paginas_visitadas}" + (" (via sitemap.xml)" if r.sitemap_usado else ""))

    if r.emails:
        L.append(f"│\n│ 📧 EMAILS ({len(r.emails)})")
        for e in r.emails[:25]:
            L.append(f"│   {e}")
        if len(r.emails) > 25:
            L.append(f"│   ... +{len(r.emails) - 25}")

    if r.telefones:
        L.append(f"│\n│ 📞 TELEFONES ({len(r.telefones)})")
        for t in r.telefones[:15]:
            fmt_t = f"({t[:2]}) {t[2:7]}-{t[7:]}" if len(t) >= 10 else t
            L.append(f"│   {fmt_t}")
        if len(r.telefones) > 15:
            L.append(f"│   ... +{len(r.telefones) - 15}")

    if r.pessoas:
        L.append(f"│\n│ 👤 PESSOAS ({len(r.pessoas)})")
        for p in r.pessoas[:20]:
            tag = f" — {p['cargo']}" if p.get("cargo") else ""
            L.append(f"│   {p['nome']}{tag}")
        if len(r.pessoas) > 20:
            L.append(f"│   ... +{len(r.pessoas) - 20}")

    if r.cnpjs:
        L.append(f"│\n│ 🏢 CNPJ: {r.cnpjs[0]}")
        if r.cnpj_dados:
            d = r.cnpj_dados
            L.append(f"│   Razão: {d.get('nome', '?')}")
            L.append(f"│   Fantasia: {d.get('fantasia', '?') or '?'}")
            L.append(f"│   Situação: {d.get('situacao', '?')}")

    if r.linkedin_empresa:
        L.append(f"│\n│ 💼 LINKEDIN EMPRESA\n│   {r.linkedin_empresa}")

    if r.linkedin_pessoas:
        L.append(f"│\n│ 🔗 LINKEDIN ({len(r.linkedin_pessoas)})")
        for li in r.linkedin_pessoas:
            L.append(f"│   {li}")

    for rede, label, urls in [
        ("instagram", "INSTAGRAM", r.instagram),
        ("facebook", "FACEBOOK", r.facebook),
        ("twitter", "TWITTER/X", r.twitter),
        ("youtube", "YOUTUBE", r.youtube),
        ("tiktok", "TIKTOK", r.tiktok),
        ("whatsapp", "WHATSAPP", r.whatsapp),
        ("telegram", "TELEGRAM", r.telegram),
    ]:
        if urls:
            L.append(f"│\n│ 📱 {label}")
            for u in urls:
                L.append(f"│   {u}")

    if r.outras_redes:
        L.append(f"│\n│ 🔗 OUTROS")
        for rd, urls in r.outras_redes.items():
            for u in urls:
                L.append(f"│   [{rd}] {u}")

    L.append("└─")
    return "\n".join(L)


def to_csv(r: Resultado) -> str:
    linhas = ["secao,chave,valor"]
    linhas.append(f"dominio,{r.dominio}")
    linhas.append(f"paginas,{r.paginas_visitadas}")
    for e in r.emails:
        linhas.append(f"email,,{e}")
    for t in r.telefones:
        fmt_t = f"({t[:2]}) {t[2:7]}-{t[7:]}" if len(t) >= 10 else t
        linhas.append(f"telefone,,{fmt_t}")
    for p in r.pessoas:
        c = p.get("cargo", "")
        linhas.append(f"pessoa,{p['nome']},{c}")
    if r.cnpjs:
        linhas.append(f"cnpj,,{r.cnpjs[0]}")
        if r.cnpj_dados:
            linhas.append(f"razao_social,,{r.cnpj_dados.get('nome', '')}")
            linhas.append(f"fantasia,,{r.cnpj_dados.get('fantasia', '')}")
    if r.linkedin_empresa:
        linhas.append(f"linkedin_empresa,,{r.linkedin_empresa}")
    for li in r.linkedin_pessoas:
        linhas.append(f"linkedin_pessoa,,{li}")
    for rede in ["instagram", "facebook", "twitter", "youtube", "tiktok", "whatsapp", "telegram"]:
        for u in getattr(r, rede, []):
            linhas.append(f"{rede},,{u}")
    return "\n".join(linhas)


# ─── MAIN ─────────────────────────────────────
def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    url = args[0]
    print(f"\n🔍 Escaneando {url}...\n", file=sys.stderr)
    r = site_contacts(url)

    if "--json" in args:
        print(json.dumps(asdict(r), ensure_ascii=False, indent=2))
    elif "--csv" in args:
        print(to_csv(r))
    else:
        print()
        print(fmt(r))


if __name__ == "__main__":
    main()
