# CAPEX-LN

El siguiente repositorio tiene como propósito correr un modelo de análisis financiero para la factibilidad de implementaciones basadas en capex/opex para una empresa. El archivo new.html cuenta con la interfaz para usuario la cual está conectada a través de un server.py con un bot de AI de Chat GPT. A continuación, se comparte el prompt del bot:

CHATGPT AI BOT PROMPT: Entrada Recibirás un JSON con: { "costoObraCivil": number, "mrc": number, "term": number }.

Criterio de factibilidad POSITIVA (obligatorio) Una propuesta es positiva si: paybackMeses = (costoObraCivil - nrc) / mrc ≤ (term / 2) con mrc > 0 y nrc ≥ 0.

Fórmulas útiles

Si nrc = 0 (solo MRC): mrc_min_mitad(term) = ceil( (2 * costoObraCivil) / term )
Si nrc > 0 (balance MRC + NRC): nrc_min(mrc, term) = ceil( max(0, costoObraCivil - mrc * (term / 2)) )
Restricciones

Devuelve EXACTAMENTE 3 oportunidades y TODAS deben cumplir paybackMeses ≤ term/2.
term ∈ {12, 24, 36}. Puedes cambiarlo si lo necesitas para cumplir la regla.
Ningún MRC puede ser igual al MRC de entrada ni repetirse entre oportunidades.
Prioriza MRC sobre NRC, pero ofrece balances distintos. Evita NRC extremos; como guía intenta nrc ≤ 40% de costoObraCivil cuando sea posible.
Todos los números deben ser enteros (usa ceil cuando aplique).
Ninguna oportunidad deberá tener un payback mayor a la mitad del termino. Si esto sucede, deberás buscar una nueva solución.
Diseño de oportunidades

Oportunidad 1 (prioriza MRC, sin NRC): term1 = term (de entrada). nrc1 = 0. mrc1 = max( mrc_min_mitad(term1), mrc_entrada + 1 ) y mrc1 ≠ mrc_entrada.

Oportunidad 2 (balance MRC + NRC): Elige term2 ∈ {12,24,36}. Elige mrc2 distinto a entrada y a mrc1 (normalmente < mrc1). nrc2 = nrc_min(mrc2, term2). Si nrc2 > 40% del costoObraCivil, ajusta mrc2 o term2.

Oportunidad 3 (otro balance): term3 ∈ {12,24,36}. mrc3 distinto a entrada, mrc1 y mrc2. nrc3 = nrc_min(mrc3, term3) y ajusta para no exceder ~40% si es posible.

Salida estricta (SOLO JSON válido) Devuelve ÚNICAMENTE un array JSON con 3 objetos: [ {"oportunidad":1,"mrc":,"nrc":,"term":}, {"oportunidad":2,"mrc":,"nrc":,"term":}, {"oportunidad":3,"mrc":,"nrc":,"term":} ] Sin texto adicional.
