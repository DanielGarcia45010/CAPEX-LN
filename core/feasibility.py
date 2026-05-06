import math


TERMS = [12, 24, 36]


def payback_months(costo, nrc, mrc):

    if mrc <= 0:
        return float("inf")

    return (costo - nrc) / mrc


def mrc_min_mitad(costo, term):

    return math.ceil((2 * costo) / term)


def nrc_min(costo, mrc, term):

    return math.ceil(
        max(
            0,
            costo - (mrc * (term / 2))
        )
    )


def valid_opportunity(costo, mrc, nrc, term):

    if mrc <= 0:
        return False

    if nrc < 0:
        return False

    pb = payback_months(costo, nrc, mrc)

    return pb <= (term / 2)


def generate_opportunities(costo, mrc_input, term_input):

    opportunities = []

    used_mrc = set([mrc_input])

    # ---------------- OPORTUNIDAD 1 ----------------
    term1 = term_input

    mrc1 = max(
        mrc_min_mitad(costo, term1),
        mrc_input + 1
    )

    nrc1 = 0

    opportunities.append({
        "oportunidad": 1,
        "mrc": int(mrc1),
        "nrc": int(nrc1),
        "term": int(term1)
    })

    used_mrc.add(mrc1)

    # ---------------- OPORTUNIDAD 2 ----------------
    found2 = False

    for term2 in TERMS:

        for delta in range(1, 500):

            mrc2 = max(
                1,
                mrc1 - delta
            )

            if mrc2 in used_mrc:
                continue

            nrc2 = nrc_min(costo, mrc2, term2)

            if nrc2 > (0.4 * costo):
                continue

            if valid_opportunity(costo, mrc2, nrc2, term2):

                opportunities.append({
                    "oportunidad": 2,
                    "mrc": int(mrc2),
                    "nrc": int(nrc2),
                    "term": int(term2)
                })

                used_mrc.add(mrc2)
                found2 = True
                break

        if found2:
            break

    # ---------------- OPORTUNIDAD 3 ----------------
    found3 = False

    for term3 in TERMS[::-1]:

        for delta in range(1, 500):

            mrc3 = max(
                1,
                mrc_input + delta + 2
            )

            if mrc3 in used_mrc:
                continue

            nrc3 = nrc_min(costo, mrc3, term3)

            if nrc3 > (0.4 * costo):
                continue

            if valid_opportunity(costo, mrc3, nrc3, term3):

                opportunities.append({
                    "oportunidad": 3,
                    "mrc": int(mrc3),
                    "nrc": int(nrc3),
                    "term": int(term3)
                })

                found3 = True
                break

        if found3:
            break

    return opportunities[:3]