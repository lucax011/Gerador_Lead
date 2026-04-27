"""Niche Classifier

Classifica o nicho de um lead usando sinais disponíveis em ordem de confiança:
  1. atividade_principal do CNPJ (texto oficial CNAE — mais confiável)
  2. Nome da empresa (company)
  3. Bio do Instagram
  4. Hint pela fonte de captura

Retorna o slug do nicho correspondente à tabela `niches`, ou None se inconclusivo.
"""
import re
import unicodedata

# ---------------------------------------------------------------------------
# Keyword maps  — slug → frozenset de termos (lowercase, sem acento via normalize)
# Cada termo é testado como substring no texto normalizado do sinal.
# Ordem dentro de SLUG_KEYWORDS não importa; a ordem de PRIORITY_ORDER sim.
# ---------------------------------------------------------------------------

SLUG_KEYWORDS: dict[str, frozenset[str]] = {
    "beleza-estetica": frozenset({
        "cabeleirei", "manicure", "pedicure", "nail", "estetica", "esteticista",
        "depilacao", "sobrancelha", "lash", "barbearia", "barbeiro", "maquiagem",
        "salao de beleza", "studio de beleza", "beauty", "spa estetico", "cilios",
        "designer de unhas", "alongamento", "micropigmentacao", "visagismo",
    }),
    "academia-fitness": frozenset({
        "academia", "personal trainer", "personal", "pilates", "crossfit",
        "musculacao", "natacao", "ginastica", "yoga", "treino", "fitness",
        "atividade fisica", "box de treinamento", "estudio de pilates",
    }),
    "saude-bem-estar": frozenset({
        "clinica medica", "clinica odontologica", "clinica de saude", "clinica de nutricao",
        "clinica de fisioterapia", "clinica de psicologia", "medico", "medica",
        "dentista", "odontologia", "nutricao", "nutricionista", "psicologia",
        "psicologo", "fisioterapia", "fisioterapeuta", "farmacia", "hospital",
        "terapeuta", "acupuntura", "oftalmo", "dermato", "pediatria", "cardiologia",
        "ortopedia", "fonoaudiologia", "terapia", "saude", "bem estar", "wellness",
    }),
    "alimentacao": frozenset({
        "restaurante", "lanchonete", "cafe", "padaria", "panificacao", "panificadora",
        "pizzaria", "sushi", "hamburger", "hamburguer", "delivery", "alimentacao",
        "gastronomia", "buffet", "confeitaria", "doceria", "sorveteria", "biscoito",
        "churrascaria", "food", "marmita", "quentinha", "brigadeiro", "bolos e doces",
        "fabricacao de paes", "fabricacao de biscoito", "fabricacao de bolo",
    }),
    "pet-shop": frozenset({
        "petshop", "pet shop", "veterinari", "veterinarias", "canil", "banho e tosa",
        "clinica veterinaria", "zootecnia", "pet", "grooming", "racao", "tosa",
        "residencia veterinaria", "animais domesticos",
    }),
    "imoveis": frozenset({
        "imobiliaria", "imoveis", "corretor de imoveis", "incorporacao",
        "empreendimento imobiliario", "loteamento", "administracao de imoveis",
        "aluguel", "vendas de imoveis",
    }),
    "educacao": frozenset({
        "escola", "colegio", "universidade", "faculdade", "curso", "treinamento",
        "educacao", "ensino", "creche", "pre-escola", "idiomas", "ingles",
        "cursos livres", "cursos profissionalizantes", "ead", "plataforma de ensino",
    }),
    "servicos-juridicos": frozenset({
        "advocacia", "advogado", "juridico", "direito", "notarial", "cartorio",
        "consultoria juridica", "escritorio de advocacia", "legaltech",
    }),
    "financeiro": frozenset({
        "seguro", "seguros", "financeiro", "financeira", "banco", "credito",
        "investimento", "corretora", "previdencia", "fintech", "cambio",
        "correspondente bancario", "emprestimo", "consorcio", "cooperativa de credito",
    }),
    "ecommerce": frozenset({
        "comercio eletronico", "e-commerce", "ecommerce", "loja virtual",
        "marketplace", "dropshipping", "varejo online", "loja online",
    }),
    "moda-vestuario": frozenset({
        "vestuario", "roupa", "moda", "boutique", "confeccao", "atacado de roupa",
        "calcados", "acessorios", "bijouteria", "moda feminina", "moda masculina",
        "moda infantil", "lingerie", "modinha",
    }),
    "tecnologia": frozenset({
        "software", "tecnologia da informacao", "informatica",
        "desenvolvimento de sistemas", "desenvolvimento de software",
        "programas de computador", "licenciamento de software",
        "programacao", "suporte tecnico", "automacao", "saas",
        "startup", "app", "aplicativo", "dados", "inteligencia artificial",
        "computacao", "telecomunicacoes",
    }),
    "construcao-reformas": frozenset({
        "construcao", "reforma", "engenharia", "arquitetura", "decoracao",
        "pintura", "eletrica", "hidraulica", "marcenaria", "jardinagem",
        "paisagismo", "instalacoes", "predial", "civil",
    }),
    "contabilidade": frozenset({
        "contabilidade", "contador", "assessoria contabil", "bpo", "fiscal",
        "tributario", "auditoria", "escritorio de contabilidade", "imposto",
        "declaracao", "nota fiscal",
    }),
    "industria": frozenset({
        "industria", "manufatura", "metalurgi", "metalurgica", "quimica",
        "textil", "plastico", "borracha", "madeira", "ceramica",
        "beneficiamento", "extracao", "mineracao", "siderurgica",
        "fundacao", "fundição", "fabricacao de plastico", "fabricacao de borracha",
        "fabricacao de metal", "fabricacao de maquinas", "fabricacao de equipamento",
    }),
}

# Source hints com menor peso — usados só quando nenhum texto classificou
SOURCE_HINTS: dict[str, str] = {
    "instagram":    "beleza-estetica",   # maioria dos leads Instagram são beleza/moda
    "google_maps":  None,                # genérico demais para inferir
    "web_scraping": None,
}


def _normalize(text: str) -> str:
    """Lowercase + remove acentos (NFD decomposition) + colapsa espaços."""
    nfd = unicodedata.normalize("NFD", text.lower())
    without_accents = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", without_accents).strip()


def _score_text(text: str) -> dict[str, int]:
    """Conta hits de keywords de cada slug num texto normalizado."""
    norm = _normalize(text)
    hits: dict[str, int] = {}
    for slug, keywords in SLUG_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in norm)
        if count:
            hits[slug] = count
    return hits


def classify_niche(
    atividade: str | None = None,
    company: str | None = None,
    bio: str | None = None,
    source_name: str | None = None,
) -> str | None:
    """
    Retorna o slug do nicho mais provável, ou None se inconclusivo.

    Confiança decrescente dos sinais:
      atividade × 3  (texto oficial CNAE)
      company   × 2  (razão social registrada)
      bio       × 1  (texto informal, emojis, gírias)
    Source hint só é usado como desempate quando o score total é zero.
    """
    scores: dict[str, float] = {}

    if atividade:
        for slug, hits in _score_text(atividade).items():
            scores[slug] = scores.get(slug, 0) + hits * 3

    if company:
        for slug, hits in _score_text(company).items():
            scores[slug] = scores.get(slug, 0) + hits * 2

    if bio:
        for slug, hits in _score_text(bio).items():
            scores[slug] = scores.get(slug, 0) + hits * 1

    if scores:
        return max(scores, key=lambda s: scores[s])

    # Fallback: hint por source (baixa confiança)
    if source_name:
        return SOURCE_HINTS.get(source_name)

    return None
