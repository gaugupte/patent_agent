# patentability_rules.py

SECTION_3_RULES = [
    {
        "id": "3(a)",
        "title": "Frivolous invention or contrary to natural laws",
        "test": ("Check whether the invention is frivolous or claims something contrary to well-established natural laws."),
    },
    {
        "id": "3(b)",
        "title": "Contrary to public order or morality",
        "test": ("Check whether the intended use of the invention is contrary to public order or morality, or causes serious prejudice to human, animal or plant life or health or the environment."),
    },
    {
        "id": "3(c)",
        "title": "Mere discovery",
        "test": ("Check whether the subject matter is merely the discovery of a scientific principle, abstract theory, or naturally occurring substance rather than a practical product or process."),
    },
    {
        "id": "3(d)",
        "title": "New form, property or use of known substance",
        "test": (
            "Check whether the invention merely claims a new form of a known "
            "substance, a new property or new use of a known substance, or "
            "a known process without the statutory requirements being met."
        ),
    },
    {
        "id": "3(e)",
        "title": "Mere admixture",
        "test": ("Check whether the subject matter is merely an admixture resulting only in aggregation of properties without the required synergistic effect."),
    },
    {
        "id": "3(f)",
        "title": "Mere arrangement or duplication of known devices",
        "test": ("Check whether the invention is merely an arrangement, re-arrangement or duplication of known devices functioning independently in a known way."),
    },
    {
        "id": "3(h)",
        "title": "Method of agriculture or horticulture",
        "test": ("Check whether the claimed subject matter is a method of agriculture or horticulture."),
    },
    {
        "id": "3(i)",
        "title": "Treatment of humans or animals",
        "test": ("Check whether the invention is a medicinal, surgical, curative, prophylactic, diagnostic, therapeutic or other treatment process for humans or animals."),
    },
    {
        "id": "3(j)",
        "title": "Plants, animals and essentially biological processes",
        "test": ("Check whether the invention concerns plants or animals, subject to statutory exceptions, or an essentially biological process for production or propagation of plants or animals."),
    },
    {
        "id": "3(k)",
        "title": ("Mathematical method, business method, computer programme per se or algorithms"),
        "test": (
            "Determine whether the claimed subject matter is merely a "
            "mathematical method, business method, computer programme per se "
            "or algorithm. Where computing/software is involved, identify "
            "whether the disclosure provides a technical solution having "
            "technical features or technical effect, rather than merely "
            "implementing a business, administrative or abstract computational "
            "scheme."
        ),
    },
    {
        "id": "3(l)",
        "title": "Literary, dramatic, musical or artistic work",
        "test": ("Check whether the subject matter is merely a literary, dramatic, musical or artistic work or another aesthetic creation."),
    },
    {
        "id": "3(m)",
        "title": "Mental act, scheme, rule or game",
        "test": ("Check whether the invention is merely a scheme, rule or method for performing a mental act or a method of playing a game."),
    },
    {
        "id": "3(n)",
        "title": "Presentation of information",
        "test": ("Check whether the claimed subject matter is merely the presentation of information."),
    },
    {
        "id": "3(o)",
        "title": "Topography of integrated circuits",
        "test": ("Check whether the subject matter is the topography of an integrated circuit."),
    },
    {
        "id": "3(p)",
        "title": "Traditional knowledge",
        "test": ("Check whether the invention is in effect traditional knowledge or merely aggregates or duplicates known properties of traditionally known components."),
    },
]


SECTION_4_RULE = {
    "id": "4",
    "title": "Inventions relating to atomic energy",
    "test": ("Check whether the invention falls within subject matter relating to atomic energy as contemplated by the Atomic Energy Act."),
}


SECTION_10_RULES = [
    {
        "id": "10(1)",
        "title": "Specification must begin with a title",
    },
    {
        "id": "10(4)(a)",
        "title": "Full and particular description",
    },
    {
        "id": "10(4)(b)",
        "title": "Best method of performing the invention",
    },
    {
        "id": "10(4)(c)",
        "title": "Claims defining scope",
    },
    {
        "id": "10(4)(d)",
        "title": "Abstract",
    },
    {
        "id": "10(5)",
        "title": "Claims must be clear, succinct and fairly based",
    },
]


RULE_13_RULES = [
    {
        "id": "13(1)",
        "title": "Specification in prescribed form",
    },
    {
        "id": "13(4)",
        "title": "Drawings where necessary",
    },
    {
        "id": "13(7)(a)",
        "title": "Abstract begins with title",
    },
    {
        "id": "13(7)(b)",
        "title": "Contents of abstract",
    },
    {
        "id": "13(7)(c)",
        "title": "Abstract length",
    },
    {
        "id": "13(7)(d)",
        "title": "Reference signs in drawings",
    },
    {
        "id": "13(7)(e)",
        "title": "Abstract as search instrument",
    },
]
