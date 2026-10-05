import os, sqlite3, secrets
from pathlib import Path
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory, flash
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE = Path(__file__).resolve().parent
DB = BASE / "data" / "memory_hub.db"
UPLOADS = BASE / "static" / "uploads"
ALLOWED = {
    "photo": {"jpg","jpeg","png","webp","gif"},
    "video": {"mp4","webm","mov"},
    "audio": {"mp3","wav","ogg","m4a"},
    "document": {"pdf","txt","doc","docx"},
}

app = Flask(__name__)
app.secret_key = os.getenv("SESSION_SECRET", secrets.token_hex(32))
app.config["MAX_CONTENT_LENGTH"] = 80 * 1024 * 1024

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "ABISHEK_BHUSAL")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")
PRIVATE_PASSWORD_HASH = os.getenv("PRIVATE_PASSWORD_HASH", "")

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS albums(
      id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT DEFAULT '',
      created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS items(
      id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT DEFAULT '',
      kind TEXT NOT NULL, filename TEXT DEFAULT '', album_id INTEGER, private INTEGER DEFAULT 0,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(album_id) REFERENCES albums(id) ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS comments(
      id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER NOT NULL, name TEXT NOT NULL,
      body TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS likes(
      id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER NOT NULL, token TEXT NOT NULL,
      UNIQUE(item_id, token), FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS notes(
      id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, body TEXT NOT NULL,
      updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS messages(
      id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT DEFAULT '',
      body TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS settings(
      key TEXT PRIMARY KEY, value TEXT NOT NULL
    );
    """)
    defaults = {
      "site_title":"ABISHEK MEMORY HUB",
      "tagline":"Your moments. Your stories. Your memories.",
      "welcome":"A beautiful private space to keep the moments that matter.",
      "about":"ABISHEK MEMORY HUB is a personal digital garden for memories, photos, videos, notes and stories."
    }
    for k,v in defaults.items():
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",(k,v))
    con.commit(); con.close()

def setting(key, fallback=""):
    con=db(); row=con.execute("SELECT value FROM settings WHERE key=?",(key,)).fetchone(); con.close()
    return row["value"] if row else fallback

@app.context_processor
def globals_():
    return {"site_title":setting("site_title","ABISHEK MEMORY HUB"),
            "tagline":setting("tagline","Your moments. Your stories. Your memories.")}

def admin_required(fn):
    @wraps(fn)
    def wrapped(*a, **kw):
        if not session.get("admin"):
            return redirect(url_for("admin_login", next=request.path))
        return fn(*a, **kw)
    return wrapped

def private_required(fn):
    @wraps(fn)
    def wrapped(*a, **kw):
        if not session.get("private"):
            return redirect(url_for("private"))
        return fn(*a, **kw)
    return wrapped

def item_rows(where="1=1", params=()):
    con=db()
    rows=con.execute(f"""SELECT i.*, a.name album_name,
      (SELECT COUNT(*) FROM likes l WHERE l.item_id=i.id) likes,
      (SELECT COUNT(*) FROM comments c WHERE c.item_id=i.id) comments
      FROM items i LEFT JOIN albums a ON a.id=i.album_id
      WHERE {where} ORDER BY i.created_at DESC""", params).fetchall()
    con.close(); return rows

@app.route("/")
def home():
    items=item_rows("i.private=0")[:12]
    con=db()
    albums=con.execute("SELECT * FROM albums ORDER BY created_at DESC LIMIT 6").fetchall()
    stats={
      "memories":con.execute("SELECT COUNT(*) FROM items WHERE private=0").fetchone()[0],
      "photos":con.execute("SELECT COUNT(*) FROM items WHERE kind='photo' AND private=0").fetchone()[0],
      "videos":con.execute("SELECT COUNT(*) FROM items WHERE kind='video' AND private=0").fetchone()[0],
      "stories":con.execute("SELECT COUNT(*) FROM items WHERE kind='story' AND private=0").fetchone()[0]
    }
    con.close()
    return render_template("home.html", items=items, albums=albums, stats=stats, welcome=setting("welcome"))

@app.route("/<kind>")
def library(kind):
    if kind not in ("photo","video","audio","story","document"):
        return redirect(url_for("home"))
    return render_template("library.html", kind=kind, items=item_rows("i.kind=? AND i.private=0",(kind,)))

@app.route("/albums")
def albums():
    con=db(); rows=con.execute("""SELECT a.*, COUNT(i.id) count FROM albums a
        LEFT JOIN items i ON i.album_id=a.id AND i.private=0 GROUP BY a.id ORDER BY a.created_at DESC""").fetchall()
    con.close(); return render_template("albums.html", albums=rows)

@app.route("/album/<int:album_id>")
def album(album_id):
    con=db(); a=con.execute("SELECT * FROM albums WHERE id=?",(album_id,)).fetchone(); con.close()
    if not a: return "Album not found",404
    return render_template("library.html", kind="album", items=item_rows("i.album_id=? AND i.private=0",(album_id,)), album=a)

@app.route("/item/<int:item_id>", methods=["GET"])
def item(item_id):
    rows=item_rows("i.id=? AND i.private=0",(item_id,))
    if not rows: return "Memory not found",404
    con=db(); comments=con.execute("SELECT * FROM comments WHERE item_id=? ORDER BY created_at DESC",(item_id,)).fetchall(); con.close()
    return render_template("item.html", item=rows[0], comments=comments)

@app.post("/item/<int:item_id>/comment")
def comment(item_id):
    name=request.form.get("name","Guest").strip()[:60]
    body=request.form.get("body","").strip()[:1000]
    if body: 
        con=db(); con.execute("INSERT INTO comments(item_id,name,body) VALUES(?,?,?)",(item_id,name or "Guest",body)); con.commit(); con.close()
    return redirect(url_for("item", item_id=item_id))

@app.post("/api/item/<int:item_id>/like")
def like(item_id):
    token=session.setdefault("visitor_token",secrets.token_hex(16))
    con=db()
    try: con.execute("INSERT INTO likes(item_id,token) VALUES(?,?)",(item_id,token)); added=True
    except sqlite3.IntegrityError: con.execute("DELETE FROM likes WHERE item_id=? AND token=?",(item_id,token)); added=False
    count=con.execute("SELECT COUNT(*) c FROM likes WHERE item_id=?",(item_id,)).fetchone()["c"]; con.commit(); con.close()
    return jsonify(ok=True, liked=added, count=count)

@app.route("/about")
def about(): return render_template("about.html", about=setting("about"))

@app.route("/contact", methods=["GET","POST"])
def contact():
    if request.method=="POST":
        name=request.form.get("name","").strip()[:80]; email=request.form.get("email","").strip()[:120]; body=request.form.get("body","").strip()[:1500]
        if name and body:
            con=db(); con.execute("INSERT INTO messages(name,email,body) VALUES(?,?,?)",(name,email,body)); con.commit(); con.close(); flash("Message sent successfully.")
        return redirect(url_for("contact"))
    return render_template("contact.html")

@app.route("/private", methods=["GET","POST"])
def private():
    if request.method=="POST":
        pw=request.form.get("password","")
        if PRIVATE_PASSWORD_HASH and check_password_hash(PRIVATE_PASSWORD_HASH,pw):
            session["private"]=True; return redirect(url_for("private"))
        flash("Private password is not configured or is incorrect.")
    items=item_rows("i.private=1") if session.get("private") else []
    return render_template("private.html", items=items, unlocked=session.get("private",False))

@app.get("/private/logout")
def private_logout(): session.pop("private",None); return redirect(url_for("private"))

@app.get("/media/<path:name>")
def media(name):
    safe=Path(name)
    for folder in ("photos","videos","audio","documents"):
        candidate=UPLOADS/folder/safe
        if candidate.exists() and candidate.is_file(): return send_from_directory(candidate.parent,candidate.name)
    return "File not found",404

@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if request.method=="POST":
        u=request.form.get("username",""); p=request.form.get("password","")
        valid = u==ADMIN_USERNAME and bool(ADMIN_PASSWORD_HASH) and check_password_hash(ADMIN_PASSWORD_HASH,p)
        if valid:
            session["admin"]=True; return redirect(request.args.get("next") or url_for("admin_dashboard"))
        flash("Invalid admin credentials.")
    return render_template("admin/login.html")

@app.get("/admin/logout")
def admin_logout(): session.clear(); return redirect(url_for("home"))

@app.get("/admin")
@admin_required
def admin_dashboard():
    con=db()
    stats={"memories":con.execute("SELECT COUNT(*) FROM items").fetchone()[0],"albums":con.execute("SELECT COUNT(*) FROM albums").fetchone()[0],"notes":con.execute("SELECT COUNT(*) FROM notes").fetchone()[0],"messages":con.execute("SELECT COUNT(*) FROM messages").fetchone()[0]}
    albums=con.execute("SELECT * FROM albums ORDER BY created_at DESC").fetchall()
    notes=con.execute("SELECT * FROM notes ORDER BY updated_at DESC").fetchall()
    messages=con.execute("SELECT * FROM messages ORDER BY created_at DESC").fetchall()
    comments=con.execute("""SELECT c.*,i.title item_title FROM comments c JOIN items i ON i.id=c.item_id ORDER BY c.created_at DESC""").fetchall()
    items=con.execute("SELECT * FROM items ORDER BY created_at DESC").fetchall()
    con.close()
    return render_template("admin/dashboard.html",stats=stats,albums=albums,notes=notes,messages=messages,comments=comments,items=items,settings={"site_title":setting("site_title"),"tagline":setting("tagline"),"welcome":setting("welcome"),"about":setting("about")})

def save_upload(file, kind):
    if not file or not file.filename: return ""
    ext=file.filename.rsplit(".",1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED.get(kind,set()): raise ValueError("Unsupported file type")
    name=secure_filename(file.filename)
    unique=f"{secrets.token_hex(8)}_{name}"
    folder={"photo":"photos","video":"videos","audio":"audio","document":"documents"}[kind]
    (UPLOADS/folder).mkdir(parents=True,exist_ok=True)
    file.save(UPLOADS/folder/unique)
    return f"{folder}/{unique}"

@app.post("/admin/item/add")
@admin_required
def add_item():
    kind=request.form.get("kind","story")
    title=request.form.get("title","Untitled").strip()[:160]
    desc=request.form.get("description","").strip()[:4000]
    private=1 if request.form.get("private") else 0
    album_id=request.form.get("album_id") or None
    filename=""
    if kind in ("photo","video","audio","document"):
        try: filename=save_upload(request.files.get("file"),kind)
        except ValueError as e: flash(str(e)); return redirect(url_for("admin_dashboard"))
    con=db(); con.execute("INSERT INTO items(title,description,kind,filename,album_id,private) VALUES(?,?,?,?,?,?)",(title,desc,kind,filename,album_id,private)); con.commit(); con.close()
    return redirect(url_for("admin_dashboard"))

@app.post("/admin/item/<int:item_id>/delete")
@admin_required
def delete_item(item_id):
    con=db(); row=con.execute("SELECT filename FROM items WHERE id=?",(item_id,)).fetchone()
    if row and row["filename"]:
        p=UPLOADS/row["filename"]
        if p.exists(): p.unlink()
    con.execute("DELETE FROM items WHERE id=?",(item_id,)); con.commit(); con.close()
    return redirect(url_for("admin_dashboard"))

@app.post("/admin/album/add")
@admin_required
def add_album():
    name=request.form.get("name","").strip()[:120]; desc=request.form.get("description","").strip()[:500]
    if name:
        con=db(); con.execute("INSERT INTO albums(name,description) VALUES(?,?)",(name,desc)); con.commit(); con.close()
    return redirect(url_for("admin_dashboard"))

@app.post("/admin/album/<int:album_id>/delete")
@admin_required
def delete_album(album_id):
    con=db(); con.execute("UPDATE items SET album_id=NULL WHERE album_id=?",(album_id,)); con.execute("DELETE FROM albums WHERE id=?",(album_id,)); con.commit(); con.close()
    return redirect(url_for("admin_dashboard"))

@app.post("/admin/note/add")
@admin_required
def add_note():
    title=request.form.get("title","Untitled").strip()[:160]; body=request.form.get("body","").strip()[:10000]
    if title and body:
        con=db(); con.execute("INSERT INTO notes(title,body) VALUES(?,?)",(title,body)); con.commit(); con.close()
    return redirect(url_for("admin_dashboard"))

@app.post("/admin/note/<int:note_id>/delete")
@admin_required
def delete_note(note_id):
    con=db(); con.execute("DELETE FROM notes WHERE id=?",(note_id,)); con.commit(); con.close(); return redirect(url_for("admin_dashboard"))

@app.post("/admin/comment/<int:comment_id>/delete")
@admin_required
def delete_comment(comment_id):
    con=db(); con.execute("DELETE FROM comments WHERE id=?",(comment_id,)); con.commit(); con.close(); return redirect(url_for("admin_dashboard"))

@app.post("/admin/message/<int:message_id>/delete")
@admin_required
def delete_message(message_id):
    con=db(); con.execute("DELETE FROM messages WHERE id=?",(message_id,)); con.commit(); con.close(); return redirect(url_for("admin_dashboard"))

@app.post("/admin/settings")
@admin_required
def save_settings():
    con=db()
    for key in ("site_title","tagline","welcome","about"):
        con.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,request.form.get(key,"").strip()))
    con.commit(); con.close(); return redirect(url_for("admin_dashboard"))

@app.context_processor
def admin_notes():
    return {}

init_db()

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
