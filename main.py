from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from firebase_config import db
from cloudinary_config import cloudinary
from ai_service import analyze_issue
import time
from firebase_admin import firestore
from fastapi.responses import JSONResponse
from datetime import datetime


app = FastAPI(
    title="Civic Issue Reporting API",
    description="Backend for Civic Issue Reporting & Govt Workflow",
    version="1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)


ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://civic-issue-frontend.onrender.com",   # (we will deploy later)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],            # temporarily allow all — safe for testing
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

@app.options("/{rest_of_path:path}")
async def preflight_handler(rest_of_path: str):
    return JSONResponse({"status": "ok"})


@app.get("/")
def home():
    return {"status": "Backend running"}


@app.options("/report-issue")
async def report_issue_preflight():
    return {"message": "CORS OK"}


@app.post("/report-issue")
async def report_issue(
    description: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    image: UploadFile = File(None)
):

    image_url = None

    # Upload image if provided
    if image:
        upload = cloudinary.uploader.upload(image.file)
        image_url = upload["secure_url"]

    # Run AI analysis (safe fallback if AI fails)
    ai_summary = analyze_issue(description)
    if isinstance(ai_summary, dict) and "error" in ai_summary:
        ai_summary = None

    issue_data = {
        "title": "Citizen Issue Report",
        "description": description,
        "latitude": latitude,
        "longitude": longitude,
        "image_url": image_url,
        "ai_summary": ai_summary,
        "status": "Pending",
        "created_at": datetime.utcnow().isoformat()
    }

    # Save into Firestore
    doc_ref, _ = db.collection("issues").add(issue_data)

    return {
        "success": True,
        "message": "Issue reported successfully",
        "issue_id": doc_ref.id,
        "maps_link": f"https://www.google.com/maps?q={latitude},{longitude}"
    }







# GET — Fetch All Issues
@app.get("/issues")
def get_issues():
    issues = []
    docs = db.collection("issues").stream()

    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        data["maps_link"] = f"https://www.google.com/maps?q={data['latitude']},{data['longitude']}"
        issues.append(data)

    return issues


# GET — Navigation Link
@app.get("/navigate/{issue_id}")
def navigate(issue_id: str):
    doc = db.collection("issues").document(issue_id).get()
    data = doc.to_dict()

    return {
        "maps_link": f"https://www.google.com/maps?q={data['latitude']},{data['longitude']}"
    }


# POST — Resolve with AI
@app.post("/resolve-with-ai")
def resolve_with_ai(description: str):
    ai_result = analyze_issue(description)

    doc_ref = db.collection("ai_analysis").add({
        "description": description,
        "category": ai_result.get("category"),
        "severity": ai_result.get("severity"),
        "department": ai_result.get("department"),
        "actions": ai_result.get("actions"),
        "status": "Pending",
        "created_at": firestore.SERVER_TIMESTAMP
    })

    return {
        "message": "AI analysis saved successfully",
        "document_id": doc_ref[1].id,
        "analysis": ai_result
    }


# POST — Update Issue Status (Govt Workflow)
@app.post("/update-status/{issue_id}")
async def update_status(
    issue_id: str,
    status: str = Form(...),        # Pending / In-Progress / Resolved
    notes: str = Form(""),          # Optional
    proof_image: UploadFile = File(None)  # Optional image
):

    issue_ref = db.collection("issues").document(issue_id)
    issue = issue_ref.get()

    if not issue.exists:
        return {"error": "Issue not found"}

    update_data = {
        "status": status,
        "notes": notes,
        "updated_at": firestore.SERVER_TIMESTAMP
    }

    # Upload proof image if provided
    if proof_image:
        upload = cloudinary.uploader.upload(proof_image.file)
        update_data["resolved_image"] = upload["secure_url"]

    # If resolved → store resolved timestamp
    if status.lower() == "resolved":
            update_data["resolved_at"] = firestore.SERVER_TIMESTAMP

    # Update record in Firestore
    issue_ref.update(update_data)

    # ---- FIX: create JSON-safe copy for API response ----
    response_data = update_data.copy()

    if "updated_at" in response_data:
        response_data["updated_at"] = "SERVER_TIMESTAMP"

    if "resolved_at" in response_data:
        response_data["resolved_at"] = "SERVER_TIMESTAMP"

    # -----------------------------------------------------

    return {
        "message": "Issue status updated successfully",
        "issue_id": issue_id,
        "update": response_data
    }


@app.get("/issues/{status}")
def get_issues_by_status(status: str):
    issues = []
    
    docs = db.collection("issues")\
        .where("status", "==", status.capitalize())\
        .stream()

    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        data["maps_link"] = f"https://www.google.com/maps?q={data['latitude']},{data['longitude']}"
        issues.append(data)

    return issues


# POST — Assign Issue to Officer
@app.post("/assign-officer/{issue_id}")
async def assign_officer(
    issue_id: str,
    officer_id: str = Form(...),
    officer_name: str = Form(...)
):

    issue_ref = db.collection("issues").document(issue_id)
    issue = issue_ref.get()

    if not issue.exists:
        return {"error": "Issue not found"}

    update_data = {
        "assigned_officer_id": officer_id,
        "assigned_officer_name": officer_name,
        "status": "In-Progress",
        "assigned_at": firestore.SERVER_TIMESTAMP
    }

    issue_ref.update(update_data)

    return {
        "message": "Officer assigned successfully",
        "issue_id": issue_id,
        "assigned_to": officer_name
    }


# GET — Issues Assigned to a Specific Officer
@app.get("/officer/issues/{officer_id}")
def get_officer_issues(officer_id: str):
    issues = []

    docs = db.collection("issues")\
        .where("assigned_officer_id", "==", officer_id)\
        .stream()

    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        data["maps_link"] = f"https://www.google.com/maps?q={data['latitude']},{data['longitude']}"
        issues.append(data)

    return issues

