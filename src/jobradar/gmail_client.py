"""Étape 1 : lire les emails d'alerte emploi dans Gmail (lecture seule)."""
import base64
import os
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
ROOT = Path(__file__).resolve().parents[2]
CREDENTIALS = ROOT / "credentials.json"
TOKEN = ROOT / "token.json"


def get_service():
    """Connexion OAuth à Gmail. Au premier lancement, une page Google s'ouvre pour autoriser."""
    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def list_alert_messages(service, query=None, max_results=50):
    """Renvoie la liste des ids des emails d'alerte."""
    query = query or os.getenv("GMAIL_QUERY")
    resp = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    return [m["id"] for m in resp.get("messages", [])]


def get_html_body(service, msg_id):
    """Renvoie (expéditeur, sujet, html) d'un email."""
    msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
    headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}

    def find_html(part):
        if part.get("mimeType") == "text/html" and part["body"].get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", "replace")
        for sub in part.get("parts", []):
            html = find_html(sub)
            if html:
                return html
        return None

    return headers.get("From", ""), headers.get("Subject", ""), find_html(msg["payload"]) or ""


if __name__ == "__main__":
    service = get_service()
    ids = list_alert_messages(service)
    print(f"{len(ids)} emails d'alerte trouvés")

    # Sauvegarde quelques emails bruts pour écrire le parseur (étape 1b)
    raw_dir = ROOT / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for msg_id in ids[:5]:
        sender, subject, html = get_html_body(service, msg_id)
        print("-", sender, "|", subject)
        (raw_dir / f"{msg_id}.html").write_text(html, encoding="utf-8")
