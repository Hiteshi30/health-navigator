from mcp.server.fastmcp import FastMCP

mcp = FastMCP("health-navigator-mcp")

# Mock database of trials
TRIALS = [
    {
        "nct_id": "NCT01123456",
        "title": "Efficacy of Novel Compound A in Treatment of Stage II Lung Cancer",
        "condition": "lung cancer",
        "status": "Recruiting",
        "location": "Boston, MA",
        "description": "This study evaluates the safety and efficacy of Compound A compared to standard chemotherapy in Stage II Non-Small Cell Lung Cancer.",
        "eligibility_criteria": "Inclusion: Pathologically confirmed Stage II NSCLC; age >= 18; ECOG performance status 0 or 1. Exclusion: Prior chest radiotherapy; history of active autoimmune disease requiring systemic immunosuppressive agents.",
        "contact_email": "lung_trials@bostonmedical.org"
    },
    {
        "nct_id": "NCT02234567",
        "title": "Immunotherapy Targeting Mutation B in Melanoma Patients",
        "condition": "melanoma",
        "status": "Recruiting",
        "location": "San Francisco, CA",
        "description": "Phase II trial assessing the objective response rate of Immunotherapy Agent B in patients with BRAF V600E mutated metastatic melanoma.",
        "eligibility_criteria": "Inclusion: Histologically confirmed metastatic melanoma; positive BRAF V600E/K mutation; age >= 18. Exclusion: Untreated brain metastases; active tuberculosis; concurrent systemic corticosteroids.",
        "contact_email": "melanoma_study@sfhealth.org"
    },
    {
        "nct_id": "NCT03345678",
        "title": "Dietary Intervention and Metformin in Type 2 Diabetes Management",
        "condition": "diabetes",
        "status": "Recruiting",
        "location": "New York, NY",
        "description": "Investigating the combined effect of low-carbohydrate diet and metformin on HbA1c levels in adults with newly diagnosed type 2 diabetes.",
        "eligibility_criteria": "Inclusion: Diagnosis of type 2 diabetes within last 6 months; HbA1c between 7.0% and 9.0%; age 18-75. Exclusion: Use of insulin; history of diabetic ketoacidosis; chronic kidney disease (eGFR < 45).",
        "contact_email": "diabetes_research@nyu.edu"
    }
]

# Mock dictionary for jargon translation
JARGON = {
    "nsclc": "Non-Small Cell Lung Cancer (the most common type of lung cancer, which grows and spreads slower than small cell lung cancer)",
    "ecog": "ECOG performance status is a scale from 0 to 5 used by doctors to assess how a patient's disease is progressing and how it affects their daily living abilities (0 means fully active, 1 means restricted in physically strenuous activity but ambulatory)",
    "metastatic": "Cancer that has spread from the primary site where it started to other parts of the body",
    "egfr": "Estimated Glomerular Filtration Rate, a test used to check how well the kidneys are working (lower values indicate poorer kidney function)",
    "hba1c": "A blood test that measures your average blood sugar levels over the past 3 months (used to diagnose and monitor diabetes)",
    "chemotherapy": "A type of cancer treatment that uses powerful drugs to destroy cancer cells",
    "radiotherapy": "A treatment using high-energy radiation (such as X-rays) to destroy cancer cells",
    "autoimmune": "A condition in which the body's immune system mistakenly attacks healthy cells",
    "corticosteroids": "A class of steroid hormones/drugs that reduce swelling, redness, itching, and allergic reactions"
}

@mcp.tool()
def search_clinical_trials(condition: str) -> list[dict]:
    """Search clinical trials for a specific medical condition (e.g., 'lung cancer', 'melanoma', 'diabetes').

    Args:
        condition: The name of the medical condition to filter trials.

    Returns:
        A list of matching clinical trials with basic information.
    """
    cond_lower = condition.lower()
    results = []
    for trial in TRIALS:
        if cond_lower in trial["condition"] or cond_lower in trial["title"].lower():
            # Return subset of info for search
            results.append({
                "nct_id": trial["nct_id"],
                "title": trial["title"],
                "condition": trial["condition"],
                "status": trial["status"],
                "location": trial["location"]
            })
    return results

@mcp.tool()
def get_trial_details(nct_id: str) -> dict:
    """Retrieve detailed information, description, and eligibility criteria for a trial by its NCT ID.

    Args:
        nct_id: The unique NCT identification number of the clinical trial (e.g., 'NCT01123456').

    Returns:
        A dictionary containing the detailed trial metadata, eligibility text, and contact information.
    """
    for trial in TRIALS:
        if trial["nct_id"].upper() == nct_id.upper():
            return trial
    return {"error": f"Clinical trial with ID {nct_id} not found."}

@mcp.tool()
def translate_jargon(term: str) -> str:
    """Translate complex medical terminology or abbreviations into simple, patient-friendly language.

    Args:
        term: The medical term or abbreviation to translate (e.g., 'NSCLC', 'ECOG', 'metastatic', 'eGFR', 'HbA1c').

    Returns:
        A patient-friendly explanation of the term.
    """
    term_key = term.lower().strip()
    # Check partial matching if exact not found
    if term_key in JARGON:
        return JARGON[term_key]
    
    for key, value in JARGON.items():
        if key in term_key or term_key in key:
            return value
            
    return f"Definition for '{term}' not found in local database, but it represents a specialized medical concept."

if __name__ == "__main__":
    mcp.run(transport="stdio")
