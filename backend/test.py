
from app.biotwin.knowledge_base import retrieve_evidence

questions = [
    "What changed in core temperature after heat acclimation?",
    "Which machine learning model performed best in PROSPIE?",
    "What are the limitations of the predictive model?",
    "How many participants were included in the heat acclimation study?",
]

for question in questions:
    print("\nQUESTION:", question)

    results = retrieve_evidence(question)

    if not results:
        print("No relevant evidence found.")
        continue

    for result in results:
        print(
            result["title"],
            "| relevance:",
            result["relevance_score"],
        )
