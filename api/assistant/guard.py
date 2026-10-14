"""Input guard: refuses what the assistant must never do, before any model call.

Pure code. The prompt also tells the model to refuse, but a refusal must not depend on the model alone. Refused:
an empty, oversized or letterless question ("{}", "???"), a question about self-harm (answered with a short supportive
message, see support_message), prompt injection, raw SQL or table access, a request for a password, key or token, a
request to change something (approve, delete, update ...) and a request for personal data (phone, IBAN, names of
customers ...).
Analytical questions pass: an action verb must open a sentence and be followed by a banking object, so
"change in approval rate", "how many applications were approved" and "Ποιο κατάστημα έχει το χαμηλότερο approval rate"
are fine.

The text is normalised first (accents, case, final sigma, zero-width characters), so the Greek patterns below are
written without accents and with a plain sigma. Known limit: encoded or obfuscated text (base64, spelled-out letters)
is not detected; it still cannot do harm, because the model has no write tool, no SQL tool and no personal data.
"""

from __future__ import annotations

import re
import unicodedata

MAX_QUESTION_CHARS = 500  # POST /assistant/query takes 3-500 characters


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[​-‏⁠﻿]", "", text)  # zero-width characters
    return re.sub(r"\s+", " ", text).casefold().strip()  # casefold also turns the final sigma into a plain one


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.DOTALL)


# ---- self-harm ----------------------------------------------------------------------------------------------------------------
# Azure OpenAI's content filter rejects such prompts with a 400, which used to surface as a 503. Catching them here means the
# model is never called, and the person gets a supportive answer instead of an error.
SELF_HARM = "self-harm"  # the reason check_question returns; the graph shows support_message(question) for it
_SELF_HARM = _rx(
    r"\b(?:suicid\w*|self[- ]?harm\w*|self[- ]?injur\w*|kill(?:ing)? my ?self|end(?:ing)? my (?:own )?life|take my (?:own )?life|"
    r"hurt(?:ing)? my ?self|cut(?:ting)? my ?self|(?:want|wanna|going) to die|wish i (?:was|were) dead|better off dead|"
    r"(?:do not|dont|don't|no longer) want to (?:live|be alive)|no reason to live|end it all)\b"
    r"|\b(?:αυτοκτον\w*|αυτοτραυματ\w*|θελω να πεθανω|θελω να (?:με )?σκοτωσω|να σκοτωσω τον εαυτο μου|"
    r"να τελειωσω (?:τη ζωη μου|με ολα)|δεν θελω να ζω|δεν αξιζει να ζω|να κανω κακο στον εαυτο μου)\b"
)
_SUPPORT_EN = (
    "I can only answer questions about the loan portfolio. If you're going through a hard time, please talk to someone you "
    "trust or call 1018 (suicide help line, Greece) or 112."
)
_SUPPORT_EL = (
    "Μπορώ να απαντώ μόνο σε ερωτήσεις για το χαρτοφυλάκιο δανείων. Αν περνάς δύσκολες στιγμές, μίλησε σε κάποιον που "
    "εμπιστεύεσαι ή κάλεσε το 1018 (Γραμμή Παρέμβασης για την Αυτοκτονία) ή το 112."
)


def support_message(question: str) -> str:
    """The short, supportive refusal for SELF_HARM, in Greek when the question has Greek letters, else in English."""
    greek = any("\u0370" <= c <= "\u03ff" or "\u1f00" <= c <= "\u1fff" for c in question or "")
    return _SUPPORT_EL if greek else _SUPPORT_EN


# ---- prompt injection -----------------------------------------------------------------------------------------------------
_INJECTION = _rx(
    r"\b(?:ignore|disregard|forget|bypass)\b.{0,40}\b(?:instructions?|prompts?|guidelines?|restrictions?|safeguards?|rules)\b"
    r"|\b(?:αγνοησ\w*|ξεχασ\w*|παρακαμψ\w*)\b.{0,40}\b(?:οδηγι\w*|κανον\w*|εντολ\w*|περιορισμ\w*)"
    r"|\b(?:system|developer|hidden|initial) (?:prompts?|instructions?|messages?)\b|\bprompt (?:injection|leak)\b"
    r"|\brepeat\b.{0,30}\b(?:text|words|message|everything) above\b"
    r"|\b(?:reveal|show|print|repeat|display)\b.{0,20}\b(?:your|the) (?:instructions|prompt|rules)\b"
    r"|\b(?:εμφανισε|δειξε|αποκαλυψε)\b.{0,20}\b(?:οδηγιεσ|prompt|κανονεσ)\b"
    r"|\byou are now\b|\bact as (?:if|an? |the )|\bpretend (?:to be|you)|\bjailbreak\b|\bdeveloper mode\b|\bdan mode\b"
    r"|\bεισαι τωρα\b|\bfrom now on\b.{0,30}\byou\b"
    r"|<\s*/?\s*(?:system|assistant|user)\s*>|\[\s*(?:system|inst)\s*\]|^\s*(?:system|assistant)\s*:"
)

# ---- raw SQL and table access -----------------------------------------------------------------------------------------------
_SQL = _rx(
    r"\bsql\b"
    r"|\bselect\b.+\bfrom\b|\bdrop\s+(?:table|database|schema)\b|\bdelete\s+from\b|\binsert\s+into\b|\bupdate\s+\w+\s+set\b"
    r"|\btruncate\s+table\b|\balter\s+table\b|\bunion\s+select\b|;\s*(?:drop|delete|insert|update|alter)\b|--\s|/\*"
    r"|\b(?:fact|dim|kpi|bronze|silver|kg)_\w+"
)

# ---- credentials ----------------------------------------------------------------------------------------------------------------
# Nothing here can reach a secret, but a question asking for one is not a portfolio question and is refused up front.
_SECRETS = _rx(
    r"\b(?:passwords?|passcodes?|api[- ]?keys?|secret keys?|private keys?|client secrets?|connection strings?|credentials?)\b"
    r"|\b(?:databricks|azure|openai|api|access|auth\w*|bearer|secret) (?:tokens?|keys?)\b"
    r"|\bκωδικοσ προσβασησ\b|\bδιαπιστευτηρια\b|\bκλειδι (?:api|προσβασησ)\b"
)

# ---- requests to change something ---------------------------------------------------------------------------------------------
_VERBS = (
    r"approve|reject|decline|deny|cancel|delete|remove|update|change|modify|edit|set|override|waive|disburse|close|freeze|"
    r"block|insert|drop|truncate|alter|write[- ]?off|increase|decrease|lower|raise|create|add|grant|issue|transfer|send|"
    r"reset|submit|disable|enable|execute|erase|wipe|purge|revoke|suspend|reopen|"
    r"ενεκριν\w*|εγκριν\w*|απορριψ\w*|διεγραψ\w*|διαγραψ\w*|σβησ\w*|αλλαξ\w*|τροποποι\w*|ακυρω\w*|αυξησ\w*|μειωσ\w*|"
    r"μπλοκαρ\w*|παγωσ\w*|ενημερωσ\w*|δημιουργησ\w*|προσθεσ\w*|μεταφερ\w*|στειλ\w*|αναστειλ\w*|ανακαλεσ\w*|"
    r"εξοφλησ\w*|χορηγησ\w*"
)
_POLITE = (
    r"please|pls|kindly|can you|could you|would you|will you|i want you to|i need you to|i would like you to|go ahead and|"
    r"hey|hi|hello|ok|okay|assistant|just|now|then|and|also|"
    r"γεια|γεια σου|παρακαλω|σε παρακαλω|μπορεισ να|θα μπορουσεσ να|θελω να|θα ηθελα να|πρεπει να|και|επισησ|τωρα|μετα"
)
# "close to 50%", "lower than 10%", "set of branches": a verb followed by a preposition is not an order
_PREPOSITION = r"(?:to|in|of|on|at|by|from|over|about|between|than)"
_ACTION = _rx(rf"^[^a-zα-ω0-9]*(?:(?:{_POLITE})[ ,]+){{0,3}}(?P<verb>{_VERBS})\b(?!\s+{_PREPOSITION}\b)(?P<rest>.*)$")
_OBJECT = _rx(
    r"\b(?:application|applicant|customer|client|loan|account|interest|rate|limit|record|row|table|data|decision|credit|"
    r"mortgage|installment|repayment|branch|product|exception|balance|exposure|status|batch|rule)\w*"
    r"|\b(?:la\d+|cu\d+|c\d{4,})\b"
    r"|\b(?:αιτησ\w*|πελατ\w*|δανει\w*|λογαριασμ\w*|επιτοκ\w*|ορι\w*|εγγραφ\w*|πινακ\w*|δεδομεν\w*|αποφασ\w*|πιστ\w*|"
    r"δοσ\w*|καταστημ\w*|προιον\w*|υπολοιπ\w*|εξαιρεσ\w*|ενυποθηκ\w*|οφειλ\w*)"
)
# "mark LA000225 as approved", "make the loan rejected": the verb is not at the start of the sentence or has no usual object
_STATUS_CHANGE = _rx(
    r"\b(?:mark|make)\b.{0,40}\b(?:la\d{6}|applications?|loans?)\b.{0,30}"
    r"\b(?:approved|rejected|declined|paid|closed|cancelled|canceled|delinquent|active)\b"
)
# a noun that only looks like a verb at the start: "change in approval rate", "αύξηση του ποσοστού"
_ANALYTICAL_LEAD = _rx(
    r"^(?:changes?|increase|decrease|updates?)\s+(?:in|of|over|on|about)\b"
    r"|^(?:αλλαγ\w*|αυξηση|μειωση|μεταβολ\w*|διαφορ\w*|ενημερωση)\b"
)

# ---- personal data ----------------------------------------------------------------------------------------------------------------
# strong terms are refused on their own
_PII_STRONG = _rx(
    r"\b(?:phone|telephone|mobile)\s+numbers?\b|\bmobile phone\b|\bcontact (?:details|info|information)\b|\biban\b"
    r"|\btax (?:id|number)\b|\bvat (?:id|number)\b|\bpassport\b|\bssn\b|\bsocial security\b|\bid card\b|\bidentity card\b"
    r"|\bdate of birth\b|\bbirth ?date\b|\bbirthday\b|\bhome address\b|\brecord[_ ]payload\b|\braw payload\b"
    r"|\bτηλεφων\w*|\bκινητο\b|\bαφμ\b|\bαμκα\b|\bταυτοτητα\b|\bδιαβατηριο\b|\bημερομηνια γεννησ\w*|\bδιευθυνση κατοικιασ\b"
)
# weak terms need a person as the subject ("email of the customer", "ονόματα πελατών")
_PII_WEAK = _rx(r"\be-?mails?\b|\baddress(?:es)?\b|\bnames?\b|\bμειλ\b|\bηλεκτρονικ\w* ταχυδρομ\w*|\bδιευθυνσ\w*|\bονομα\w*|\bεπωνυμ\w*")
_PERSON = _rx(
    r"\b(?:customers?|clients?|borrowers?|applicants?|person|people|individuals?|someone|somebody|his|her|their|him|them|"
    r"πελατ\w*|δανειοληπτ\w*|αιτουντ\w*|αιτητ\w*|ατομ\w*|προσωπ\w*|c\d{4,}|cu\d+|la\d{6})\b|customer:\w+"
)
_WHO_IS = _rx(r"\bwho\s+(?:is|are|was|were)\s+(?:the\s+)?(?:customers?|clients?|borrowers?|applicants?)\b|\bποιοσ ειναι (?:ο|η) (?:πελατησ|αιτων)\b")
_AGGREGATE_LEAD = _rx(
    r"^(?:how many|how much|number of|count|what (?:is the )?(?:percentage|share|proportion|number|rate)|percentage|share|proportion|"
    r"ποσ\w*|ποσοστο\w*|αριθμοσ)\b"
)


def _is_action(sentence: str) -> bool:
    match = _ACTION.match(sentence)
    return bool(match and not _ANALYTICAL_LEAD.match(sentence) and _OBJECT.search(match.group("rest")))


def check_question(question: str) -> str | None:
    """None if the question may go on; otherwise a short reason for refusing it."""
    if len(question or "") > MAX_QUESTION_CHARS:
        return "question too long"
    text = _normalise(question or "")
    if not text:
        return "empty question"
    if not any(c.isalpha() for c in text):  # "{}", "[]", "**", "???", "12345": nothing to answer, the model would guess
        return "no question text"
    if _SELF_HARM.search(text):
        return SELF_HARM
    if _INJECTION.search(text):
        return "prompt injection"
    if _SQL.search(text):
        return "raw SQL request"
    if _SECRETS.search(text):
        return "credentials request"
    if _STATUS_CHANGE.search(text) or any(_is_action(s.strip()) for s in re.split(r"[.!?;\n]+", text) if s.strip()):
        return "action request"
    if _PII_STRONG.search(text) or _WHO_IS.search(text):
        return "personal data"
    if _PII_WEAK.search(text) and _PERSON.search(text) and not _AGGREGATE_LEAD.match(text):
        return "personal data"
    return None
