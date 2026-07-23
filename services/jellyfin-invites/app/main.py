import httpx
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from argon2 import PasswordHasher
from cryptography.fernet import Fernet
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware


APP_DATA_DIR = Path(
    os.getenv("APP_DATA_DIR", "/app/data")
)

APP_DATA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

DATABASE_PATH = APP_DATA_DIR / "database.db"

JELLYFIN_URL = os.getenv("JELLYFIN_URL")
JELLYFIN_API_KEY = os.getenv("JELLYFIN_API_KEY")
INVITE_ENCRYPTION_KEY = os.getenv(
    "INVITE_ENCRYPTION_KEY"
)

ADMIN_USERNAME = os.getenv(
    "INVITE_ADMIN_USERNAME",
    "admin",
)

ADMIN_PASSWORD = os.getenv(
    "INVITE_ADMIN_PASSWORD"
)

SESSION_SECRET = os.getenv(
    "SESSION_SECRET"
)


if not JELLYFIN_URL:
    raise RuntimeError(
        "JELLYFIN_URL doit être défini dans l'environnement"
    )

if not JELLYFIN_API_KEY:
    raise RuntimeError(
        "JELLYFIN_API_KEY doit être défini dans l'environnement"
    )

if not INVITE_ENCRYPTION_KEY:
    raise RuntimeError(
        "INVITE_ENCRYPTION_KEY doit être défini dans l'environnement"
    )

if not ADMIN_PASSWORD:
    raise RuntimeError(
        "INVITE_ADMIN_PASSWORD doit être défini dans l'environnement"
    )

if not SESSION_SECRET:
    raise RuntimeError(
        "SESSION_SECRET doit être défini dans l'environnement"
    )


fernet = Fernet(
    INVITE_ENCRYPTION_KEY.encode()
)

password_hasher = PasswordHasher()


app = FastAPI(
    title="Jellyfin Invites"
)


app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    https_only=True,
    same_site="lax",
)


# ============================================================
# BIBLIOTHÈQUES JELLYFIN
# ============================================================

JELLYFIN_LIBRARIES = {
    "Animé": "32a6905861f48fa668fd8dc8d6c1a78c",
    "Films": "db4c1708cbb5dd1676284a40f2950aba",
    "Livres": "a79997cfec5906b035aeb50a6c3704c6",
    "Séries": "d565273fd114d77bdf349a2896867069",
    "Vidéos et photos personnelles":
        "93e019d0c4f5e6b770e13ffb45163c5d",
}


# ============================================================
# BASE DE DONNÉES
# ============================================================

def get_db():
    connection = sqlite3.connect(
        DATABASE_PATH
    )

    connection.row_factory = sqlite3.Row

    return connection


def init_database():

    with get_db() as db:

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS invitations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT UNIQUE NOT NULL,
                expires_at TEXT NOT NULL,
                max_uses INTEGER NOT NULL DEFAULT 1,
                uses INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS access_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invitation_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                password_encrypted TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                FOREIGN KEY (invitation_id)
                    REFERENCES invitations(id)
            )
            """
        )

        columns = {
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(access_requests)"
            ).fetchall()
        }

        if "password_encrypted" not in columns:

            db.execute(
                """
                ALTER TABLE access_requests
                ADD COLUMN password_encrypted TEXT
                """
            )

        existing_admin = db.execute(
            """
            SELECT id
            FROM admin_users
            WHERE username = ?
            """,
            (
                ADMIN_USERNAME,
            ),
        ).fetchone()

        if not existing_admin:

            db.execute(
                """
                INSERT INTO admin_users (
                    username,
                    password_hash,
                    created_at
                )
                VALUES (?, ?, ?)
                """,
                (
                    ADMIN_USERNAME,
                    password_hasher.hash(
                        ADMIN_PASSWORD
                    ),
                    datetime.now(
                        timezone.utc
                    ).isoformat(),
                ),
            )

        db.commit()


@app.on_event("startup")
def startup():

    init_database()


# ============================================================
# AUTHENTIFICATION ADMIN
# ============================================================

def is_admin(
    request: Request,
) -> bool:

    return bool(
        request.session.get(
            "admin_authenticated"
        )
    )


def require_admin(
    request: Request,
):

    if not is_admin(request):

        return RedirectResponse(
            "/admin/login",
            status_code=303,
        )

    return None


# ============================================================
# API JELLYFIN
# ============================================================

def jellyfin_headers():

    return {
        "X-Emby-Token": JELLYFIN_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def get_jellyfin_users():

    response = httpx.get(
        f"{JELLYFIN_URL.rstrip('/')}/Users",
        headers=jellyfin_headers(),
        timeout=10.0,
    )

    response.raise_for_status()

    return response.json()


def get_jellyfin_user(
    username: str,
):

    for user in get_jellyfin_users():

        if user["Name"].lower() == username.lower():

            return user

    return None


def create_jellyfin_user(
    username: str,
    password: str,
):

    response = httpx.post(
        f"{JELLYFIN_URL.rstrip('/')}/Users/New",
        headers=jellyfin_headers(),
        json={
            "Name": username,
            "Password": password,
        },
        timeout=10.0,
    )

    response.raise_for_status()

    user = response.json()

    return user["Id"]


def delete_jellyfin_user(
    user_id: str,
):

    response = httpx.delete(
        f"{JELLYFIN_URL.rstrip('/')}/Users/{user_id}",
        headers=jellyfin_headers(),
        timeout=10.0,
    )

    response.raise_for_status()


def get_jellyfin_user_policy(
    user_id: str,
):

    response = httpx.get(
        f"{JELLYFIN_URL.rstrip('/')}/Users",
        headers=jellyfin_headers(),
        timeout=10.0,
    )

    response.raise_for_status()

    for user in response.json():

        if user["Id"] == user_id:

            policy = user.get(
                "Policy"
            )

            if not policy:

                raise RuntimeError(
                    "La Policy Jellyfin est absente"
                )

            return policy

    raise RuntimeError(
        "Utilisateur Jellyfin introuvable"
    )


def apply_jellyfin_policy(
    user_id: str,
    library_ids: list[str],
    allow_download: bool,
):

    base_url = JELLYFIN_URL.rstrip("/")

    users_response = httpx.get(
        f"{base_url}/Users",
        headers=jellyfin_headers(),
        timeout=10.0,
    )

    users_response.raise_for_status()

    user = next(
        (
            user
            for user in users_response.json()
            if user["Id"] == user_id
        ),
        None,
    )

    if not user:

        raise RuntimeError(
            "Utilisateur Jellyfin introuvable"
        )

    policy = user.get(
        "Policy",
        {},
    ).copy()

    policy.update(
        {
            "IsAdministrator": False,
            "EnableContentDeletion": False,
            "EnableCollectionManagement": False,
            "EnableMediaPlayback": True,
            "EnableRemoteAccess": True,
        }
    )

    policy.update(
        {
            "EnableAllFolders": False,
            "EnabledFolders": library_ids,
            "EnableContentDownloading": allow_download,
        }
    )

    response = httpx.post(
        f"{base_url}/Users/{user_id}/Policy",
        headers=jellyfin_headers(),
        json=policy,
        timeout=10.0,
    )

    response.raise_for_status()


# ============================================================
# PAGE D'ACCUEIL
# ============================================================

@app.get(
    "/",
    response_class=HTMLResponse,
)
def home():

    return """
    <html>
        <head>
            <title>Jellyfin Invites</title>
        </head>

        <body>

            <h1>Jellyfin Invites</h1>

            <p>
                Portail d'invitations Jellyfin.
            </p>

            <p>
                <a href="/admin/login">
                    Administration
                </a>
            </p>

        </body>
    </html>
    """


# ============================================================
# LOGIN ADMIN
# ============================================================

@app.get(
    "/admin/login",
    response_class=HTMLResponse,
)
def admin_login_page():

    return """
    <html>
        <head>
            <title>Administration</title>
        </head>

        <body>

            <h1>Administration</h1>

            <form method="post">

                <label>
                    Nom d'utilisateur
                </label>

                <input
                    type="text"
                    name="username"
                    required
                >

                <br><br>

                <label>
                    Mot de passe
                </label>

                <input
                    type="password"
                    name="password"
                    required
                >

                <br><br>

                <button type="submit">
                    Connexion
                </button>

            </form>

        </body>
    </html>
    """


@app.post("/admin/login")
def admin_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):

    with get_db() as db:

        admin = db.execute(
            """
            SELECT *
            FROM admin_users
            WHERE username = ?
            """,
            (
                username,
            ),
        ).fetchone()

    if not admin:

        return HTMLResponse(
            "Identifiants invalides",
            status_code=401,
        )

    try:

        password_hasher.verify(
            admin["password_hash"],
            password,
        )

    except Exception:

        return HTMLResponse(
            "Identifiants invalides",
            status_code=401,
        )

    request.session[
        "admin_authenticated"
    ] = True

    return RedirectResponse(
        "/admin",
        status_code=303,
    )


# ============================================================
# DASHBOARD ADMIN
# ============================================================

@app.get(
    "/admin",
    response_class=HTMLResponse,
)
def admin_dashboard(
    request: Request,
):

    redirect = require_admin(
        request
    )

    if redirect:

        return redirect

    with get_db() as db:

        invitations = db.execute(
            """
            SELECT *
            FROM invitations
            ORDER BY created_at DESC
            """
        ).fetchall()

        requests = db.execute(
            """
            SELECT
                access_requests.*,
                invitations.token
            FROM access_requests
            JOIN invitations
                ON invitations.id =
                   access_requests.invitation_id
            ORDER BY access_requests.created_at DESC
            """
        ).fetchall()

    invitation_rows = ""

    for invitation in invitations:

        invitation_rows += f"""
        <tr>

            <td>
                {invitation["token"]}
            </td>

            <td>
                {invitation["expires_at"]}
            </td>

            <td>
                {invitation["uses"]}
                /
                {invitation["max_uses"]}
            </td>

            <td>
                <a href="/invite/{invitation["token"]}">
                    Ouvrir
                </a>
            </td>

        </tr>
        """

    request_rows = ""

    for access_request in requests:

        actions = ""

        if access_request["status"] == "pending":

            library_options = ""

            for name, library_id in (
                JELLYFIN_LIBRARIES.items()
            ):

                library_options += f"""
                <label>
                    <input
                        type="checkbox"
                        name="library_ids"
                        value="{library_id}"
                    >

                    {name}

                </label>

                <br>
                """

            actions = f"""

            <form
                method="post"
                action="/admin/requests/{access_request["id"]}/approve"
            >

                <h4>
                    Bibliothèques accessibles
                </h4>

                {library_options}

                <br>

                <label>

                    <input
                        type="checkbox"
                        name="allow_download"
                        value="1"
                    >

                    Autoriser le téléchargement

                </label>

                <br><br>

                <button type="submit">

                    Approuver et créer le compte

                </button>

            </form>

            <br>

            <form
                method="post"
                action="/admin/requests/{access_request["id"]}/reject"
            >

                <button type="submit">

                    Refuser

                </button>

            </form>

            """

        request_rows += f"""
        <tr>

            <td>
                {access_request["username"]}
            </td>

            <td>
                {access_request["status"]}
            </td>

            <td>
                {access_request["created_at"]}
            </td>

            <td>
                {actions}
            </td>

        </tr>
        """

    return f"""

    <html>

        <head>

            <title>
                Administration Jellyfin Invites
            </title>

        </head>

        <body>

            <h1>
                Administration Jellyfin Invites
            </h1>

            <h2>
                Créer une invitation
            </h2>

            <form
                method="post"
                action="/admin/invitations"
            >

                <label>
                    Durée de validité en jours
                </label>

                <input
                    type="number"
                    name="days"
                    value="7"
                    min="1"
                    max="365"
                    required
                >

                <button type="submit">

                    Créer une invitation

                </button>

            </form>

            <h2>
                Invitations
            </h2>

            <table
                border="1"
                cellpadding="8"
            >

                <tr>

                    <th>
                        Token
                    </th>

                    <th>
                        Expiration
                    </th>

                    <th>
                        Utilisations
                    </th>

                    <th>
                        Lien
                    </th>

                </tr>

                {invitation_rows}

            </table>

            <h2>
                Demandes d'accès
            </h2>

            <table
                border="1"
                cellpadding="8"
            >

                <tr>

                    <th>
                        Utilisateur
                    </th>

                    <th>
                        Statut
                    </th>

                    <th>
                        Date
                    </th>

                    <th>
                        Actions
                    </th>

                </tr>

                {request_rows}

            </table>

        </body>

    </html>

    """


# ============================================================
# CRÉATION D'INVITATION
# ============================================================

@app.post(
    "/admin/invitations"
)
def create_invitation(
    request: Request,
    days: int = Form(...),
):

    redirect = require_admin(
        request
    )

    if redirect:

        return redirect

    if days < 1 or days > 365:

        return HTMLResponse(
            "Durée invalide",
            status_code=400,
        )

    token = secrets.token_urlsafe(
        32
    )

    now = datetime.now(
        timezone.utc
    )

    expires_at = (
        now
        + timedelta(days=days)
    ).isoformat()

    with get_db() as db:

        db.execute(
            """
            INSERT INTO invitations (
                token,
                expires_at,
                max_uses,
                uses,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                token,
                expires_at,
                1,
                0,
                now.isoformat(),
            ),
        )

        db.commit()

    return RedirectResponse(
        "/admin",
        status_code=303,
    )


# ============================================================
# PAGE D'INVITATION
# ============================================================

@app.get(
    "/invite/{token}",
    response_class=HTMLResponse,
)
def invitation_page(
    token: str,
):

    with get_db() as db:

        invitation = db.execute(
            """
            SELECT *
            FROM invitations
            WHERE token = ?
            """,
            (
                token,
            ),
        ).fetchone()

    if not invitation:

        return HTMLResponse(
            "Invitation invalide",
            status_code=404,
        )

    expires_at = datetime.fromisoformat(
        invitation["expires_at"]
    )

    if expires_at <= datetime.now(
        timezone.utc
    ):

        return HTMLResponse(
            "Invitation expirée",
            status_code=410,
        )

    if (
        invitation["uses"]
        >= invitation["max_uses"]
    ):

        return HTMLResponse(
            "Invitation déjà utilisée",
            status_code=410,
        )

    return f"""

    <html>

        <head>

            <title>
                Invitation Jellyfin
            </title>

        </head>

        <body>

            <h1>
                Invitation Jellyfin
            </h1>

            <form method="post">

                <label>
                    Nom d'utilisateur Jellyfin
                </label>

                <input
                    type="text"
                    name="username"
                    minlength="3"
                    maxlength="64"
                    required
                >

                <br><br>

                <label>
                    Mot de passe
                </label>

                <input
                    type="password"
                    name="password"
                    minlength="12"
                    required
                >

                <br><br>

                <label>
                    Confirmation du mot de passe
                </label>

                <input
                    type="password"
                    name="password_confirmation"
                    minlength="12"
                    required
                >

                <br><br>

                <button type="submit">

                    Demander l'accès

                </button>

            </form>

        </body>

    </html>

    """


# ============================================================
# DEMANDE D'ACCÈS
# ============================================================

@app.post(
    "/invite/{token}"
)
def submit_access_request(
    token: str,
    username: str = Form(...),
    password: str = Form(...),
    password_confirmation: str = Form(...),
):

    username = username.strip()

    if password != password_confirmation:

        return HTMLResponse(
            "Les mots de passe ne correspondent pas",
            status_code=400,
        )

    if len(password) < 12:

        return HTMLResponse(
            "Le mot de passe doit contenir au moins 12 caractères",
            status_code=400,
        )

    if len(username) < 3:

        return HTMLResponse(
            "Nom d'utilisateur invalide",
            status_code=400,
        )

    with get_db() as db:

        invitation = db.execute(
            """
            SELECT *
            FROM invitations
            WHERE token = ?
            """,
            (
                token,
            ),
        ).fetchone()

        if not invitation:

            return HTMLResponse(
                "Invitation invalide",
                status_code=404,
            )

        expires_at = datetime.fromisoformat(
            invitation["expires_at"]
        )

        if expires_at <= datetime.now(
            timezone.utc
        ):

            return HTMLResponse(
                "Invitation expirée",
                status_code=410,
            )

        if (
            invitation["uses"]
            >= invitation["max_uses"]
        ):

            return HTMLResponse(
                "Invitation déjà utilisée",
                status_code=410,
            )

        password_encrypted = fernet.encrypt(
            password.encode()
        ).decode()

        db.execute(
            """
            INSERT INTO access_requests (
                invitation_id,
                username,
                password_hash,
                password_encrypted,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                invitation["id"],
                username,
                password_hasher.hash(
                    password
                ),
                password_encrypted,
                "pending",
                datetime.now(
                    timezone.utc
                ).isoformat(),
            ),
        )

        db.execute(
            """
            UPDATE invitations
            SET uses = uses + 1
            WHERE id = ?
            """,
            (
                invitation["id"],
            ),
        )

        db.commit()

    return HTMLResponse(
        """
        <h1>
            Demande envoyée
        </h1>

        <p>
            Ta demande a été envoyée à l'administrateur.
        </p>
        """,
        status_code=201,
    )


# ============================================================
# APPROBATION
# ============================================================

@app.post(
    "/admin/requests/{request_id}/approve"
)
def approve_request(
    request: Request,
    request_id: int,
    library_ids: list[str] = Form(
        default=[]
    ),
    allow_download: str | None = Form(
        default=None
    ),
):

    redirect = require_admin(
        request
    )

    if redirect:

        return redirect

    if not library_ids:

        return HTMLResponse(
            "Sélectionne au moins une bibliothèque",
            status_code=400,
        )

    allowed_library_ids = set(
        JELLYFIN_LIBRARIES.values()
    )

    invalid_library_ids = (
        set(library_ids)
        - allowed_library_ids
    )

    if invalid_library_ids:

        return HTMLResponse(
            "Bibliothèque invalide",
            status_code=400,
        )

    allow_download_bool = (
        allow_download == "1"
    )

    with get_db() as db:

        access_request = db.execute(
            """
            SELECT *
            FROM access_requests
            WHERE id = ?
            AND status = 'pending'
            """,
            (
                request_id,
            ),
        ).fetchone()

        if not access_request:

            return HTMLResponse(
                "Demande introuvable ou déjà traitée",
                status_code=404,
            )

        encrypted_password = (
            access_request[
                "password_encrypted"
            ]
        )

        if not encrypted_password:

            return HTMLResponse(
                "Mot de passe chiffré absent",
                status_code=500,
            )

        try:

            password = fernet.decrypt(
                encrypted_password.encode()
            ).decode()

        except Exception:

            return HTMLResponse(
                "Impossible de déchiffrer le mot de passe",
                status_code=500,
            )

        username = access_request[
            "username"
        ]

        existing_user = get_jellyfin_user(
            username
        )

        if existing_user:

            return HTMLResponse(
                (
                    "L'utilisateur Jellyfin "
                    f"'{username}' existe déjà"
                ),
                status_code=409,
            )

        user_id = None

        try:

            # 1. Création de l'utilisateur
            user_id = create_jellyfin_user(
                username=username,
                password=password,
            )

            # 2. Application de la Policy
            apply_jellyfin_policy(
                user_id=user_id,
                library_ids=library_ids,
                allow_download=(
                    allow_download_bool
                ),
            )

        except httpx.HTTPStatusError as error:

            if user_id:

                try:

                    delete_jellyfin_user(
                        user_id
                    )

                except Exception:

                    pass

            return HTMLResponse(
                f"""
                <h1>
                    Erreur Jellyfin
                </h1>

                <p>
                    HTTP
                    {error.response.status_code}
                </p>

                <pre>
                {error.response.text}
                </pre>

                <p>
                    La demande reste en attente.
                </p>
                """,
                status_code=502,
            )

        except Exception as error:

            if user_id:

                try:

                    delete_jellyfin_user(
                        user_id
                    )

                except Exception:

                    pass

            return HTMLResponse(
                f"""
                <h1>
                    Erreur lors de la création du compte
                </h1>

                <pre>
                {error}
                </pre>

                <p>
                    La demande reste en attente.
                </p>
                """,
                status_code=500,
            )

        # 3. Tout a réussi
        db.execute(
            """
            UPDATE access_requests
            SET status = 'approved'
            WHERE id = ?
            AND status = 'pending'
            """,
            (
                request_id,
            ),
        )

        db.commit()

    return RedirectResponse(
        "/admin",
        status_code=303,
    )


# ============================================================
# REFUS
# ============================================================

@app.post(
    "/admin/requests/{request_id}/reject"
)
def reject_request(
    request: Request,
    request_id: int,
):

    redirect = require_admin(
        request
    )

    if redirect:

        return redirect

    with get_db() as db:

        db.execute(
            """
            UPDATE access_requests
            SET status = 'rejected'
            WHERE id = ?
            AND status = 'pending'
            """,
            (
                request_id,
            ),
        )

        db.commit()

    return RedirectResponse(
        "/admin",
        status_code=303,
    )
