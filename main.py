from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from firebase_config import db
from cloudinary_config import cloudinary
from ai_service import analyze_issue
import json
from firebase_admin import firestore
from fastapi.responses import JSONResponse
from datetime import datetime
from auth_config import verify_user

app = FastAPI(
    title="Civic Issue Reporting API",
    description="Backend for Civic Issue Reporting & Govt Workflow",
    version="1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)


# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {"status": "Backend running"}


@app.options("/{rest_of_path:path}")
async def preflight_handler(rest_of_path: str):
    return JSONResponse({"status": "ok"})


@app.options("/report-issue")
async def report_issue_preflight():
    return {"message": "CORS OK"}



# ============================================================
# 🚀 Citizen — Report Issue (Gemini Auto-Analysis)
# ============================================================
@app.post("/report-issue")
async def report_issue(
    description: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    image: UploadFile = File(None)
):

    image_url = None

    # Upload image to Cloudinary
    if image:
        upload = cloudinary.uploader.upload(image.file)
        image_url = upload["secure_url"]


    # -------------------------------
    # 🤖 Run Gemini AI (Safe Parse)
    # -------------------------------
    try:
        ai_text = analyze_issue(description)
        ai_json = json.loads(ai_text)
    except Exception:
        ai_json = {
            "ai_summary": None,
            "severity": "Pending",
            "risk_level": None,
            "priority_score": None,
            "category": "Other",
            "department": "Municipality",
            "suggested_actions": []
        }


    # -------------------------------
    # 🧾 Save Issue Record
    # -------------------------------
    issue_data = {
        "title": "Citizen Issue Report",
        "description": description,
        "latitude": latitude,
        "longitude": longitude,
        "image_url": image_url,
        "status": "Pending",
        "created_at": datetime.utcnow().isoformat(),

        # AI Fields
        "ai_summary": ai_json.get("ai_summary"),
        "severity": ai_json.get("severity"),
        "risk_level": ai_json.get("risk_level"),
        "priority_score": ai_json.get("priority_score"),
        "category": ai_json.get("category"),
        "department": ai_json.get("department"),
        "suggested_actions": ai_json.get("suggested_actions"),
    }

    doc_ref = db.collection("issues").add(issue_data)[1]

    return {
        "success": True,
        "message": "Issue reported successfully",
        "issue_id": doc_ref.id,
        "maps_link": f"https://www.google.com/maps?q={latitude},{longitude}"
    }



# ============================================================
# 📌 Fetch All Issues
# ============================================================
@app.get("/issues")
def get_issues():
    issues = []

    docs = db.collection("issues").stream()

    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id

        lat = data.get("latitude")
        lon = data.get("longitude")

        data["maps_link"] = (
            f"https://www.google.com/maps?q={lat},{lon}"
            if lat and lon else None
        )

        issues.append(data)

    return issues



# ============================================================
# 📍 Google Maps Redirect
# ============================================================
@app.get("/navigate/{issue_id}")
def navigate(issue_id: str):
    doc = db.collection("issues").document(issue_id).get()
    data = doc.to_dict()

    return {
        "maps_link": f"https://www.google.com/maps?q={data['latitude']},{data['longitude']}"
    }



# ============================================================
# 🤖 Manual AI Analysis Endpoint (Optional)
# ============================================================
@app.post("/resolve-with-ai")
def resolve_with_ai(description: str):

    ai_json = json.loads(analyze_issue(description))

    doc_ref = db.collection("ai_analysis").add({
        "description": description,
        **ai_json
    })

    return {
        "message": "AI analysis completed",
        "document_id": doc_ref[1].id,
        "analysis": ai_json
    }



# ============================================================
# 🟡 Government — Update Issue Status
# ============================================================
@app.post("/update-status/{issue_id}")
async def update_status(
    issue_id: str,
    status: str = Form(...),
    notes: str = Form(""),
    proof_image: UploadFile = File(None)
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

    if proof_image:
        upload = cloudinary.uploader.upload(proof_image.file)
        update_data["resolved_image"] = upload["secure_url"]

    if status.lower() == "resolved":
        update_data["resolved_at"] = firestore.SERVER_TIMESTAMP

    issue_ref.update(update_data)

    return {
        "message": "Issue status updated successfully",
        "issue_id": issue_id,
        "update": {
            **update_data,
            "updated_at": "SERVER_TIMESTAMP",
            "resolved_at": "SERVER_TIMESTAMP"
                if "resolved_at" in update_data else None
        }
    }



# ============================================================
# 🟢 Assign Officer
# ============================================================
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

    issue_ref.update({
        "assigned_officer_id": officer_id,
        "assigned_officer_name": officer_name,
        "status": "In-Progress",
        "assigned_at": firestore.SERVER_TIMESTAMP
    })

    return {
        "message": "Officer assigned successfully",
        "issue_id": issue_id,
        "assigned_to": officer_name
    }



# ============================================================
# 👮 Officer — View Assigned Issues
# ============================================================
@app.get("/officer/issues/{officer_id}")
def get_officer_issues(officer_id: str):

    issues = []

    docs = db.collection("issues") \
        .where("assigned_officer_id", "==", officer_id) \
        .stream()

    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        data["maps_link"] = (
            f"https://www.google.com/maps?q={data['latitude']},{data['longitude']}"
        )
        issues.append(data)

    return issues


from fastapi import Body
#Login
@app.post("/login")
async def login(user: dict = Body(...)):

    role = user.get("role")
    username = user.get("username")
    password = user.get("password")

    found_user = verify_user(role, username, password)

    if not found_user:
        return {"success": False, "message": "Invalid credentials"}

    return {
        "success": True,
        "message": "Login successful",
        "user": {
            "id": found_user["id"],
            "name": found_user.get("name"),
            "role": found_user.get("role"),
        }
    }