from firebase_config import db

def verify_user(role: str, username: str, password: str):
    users_ref = db.collection("users")

    docs = users_ref.where("role", "==", role).stream()

    for doc in docs:
        user = doc.to_dict()

        if (
            user.get("username") == username
            and user.get("password") == password
        ):
            user["id"] = doc.id
            return user

    return None