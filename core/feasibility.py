import math


# ---------------- PAYBACK ----------------
def payback_months(costo, nrc, mrc):
    if mrc <= 0:
        return float("inf")
    return (costo - nrc) / mrc


# ---------------- VALIDACIÓN ----------------
def is_valid(costo, mrc, nrc, term):
    if mrc <= 0:
        return False

    pb = payback_months(costo, nrc, mrc)
    return pb <= (term / 2)


# ---------------- COSTOS ----------------
def get_mrc_min(costo, term):
    return math.ceil((2 * costo) / term)


def get_nrc_min(costo, mrc, term):
    return math.ceil(max(0, costo - (mrc * (term / 2))))


# ---------------- GENERADOR PRINCIPAL ----------------
def generate_opportunities(costo, mrc_input, term_input):

    opportunities = []
    used_mrc = set()

    # =====================================================
    # OPORTUNIDAD 1 → solo MRC (sin NRC)
    # =====================================================
    term1 = term_input

    mrc1 = max(
        get_mrc_min(costo, term1),
        mrc_input + 1
    )

    nrc1 = 0

    opportunities.append({
        "oportunidad": 1,
        "mrc": int(mrc1),
        "nrc": int(nrc1),
        "term": int(term1),
        "payback": payback_months(costo, nrc1, mrc1)
    })

    used_mrc.add(mrc1)

    # =====================================================
    # OPORTUNIDAD 2 → balance
    # =====================================================
    for term2 in [12, 24, 36]:

        for delta in range(1, 20000):

            mrc2 = mrc_input + delta

            if mrc2 in used_mrc:
                continue

            nrc2 = get_nrc_min(costo, mrc2, term2)

            if nrc2 > 0.4 * costo:
                continue

            if is_valid(costo, mrc2, nrc2, term2):

                opportunities.append({
                    "oportunidad": 2,
                    "mrc": int(mrc2),
                    "nrc": int(nrc2),
                    "term": int(term2),
                    "payback": payback_months(costo, nrc2, mrc2)
                })

                used_mrc.add(mrc2)
                break

        if len(opportunities) >= 2:
            break

    # =====================================================
    # OPORTUNIDAD 3 → alternativa agresiva
    # =====================================================
    for term3 in [36, 24, 12]:

        for delta in range(5000, 40000):

            mrc3 = max(1, mrc_input - delta)

            if mrc3 in used_mrc:
                continue

            nrc3 = get_nrc_min(costo, mrc3, term3)

            if nrc3 > 0.4 * costo:
                continue

            if is_valid(costo, mrc3, nrc3, term3):

                opportunities.append({
                    "oportunidad": 3,
                    "mrc": int(mrc3),
                    "nrc": int(nrc3),
                    "term": int(term3),
                    "payback": payback_months(costo, nrc3, mrc3)
                })

                break

        if len(opportunities) >= 3:
            break

    return opportunities[:3]