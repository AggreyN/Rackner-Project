# Getting Started — Week 1 (macOS)

This is your Day-1 walkthrough, Aggrey. Goal: by the end you have a working dev environment, the repo set up with the right folder structure, a Postgres database running locally, and a Python script that connects to it and prints the database version. That's your entire Week 1 deadline — and this guide gets you there step by step.

Take it slowly. Run one block at a time. If something errors, copy the error and ask me — that's normal and expected.

---

## Step 0 — Install the tools (one time)

Open the **Terminal** app (Cmd+Space, type "Terminal").

**1. Install Homebrew** (the macOS package manager). Skip if you already have it (`brew --version` works):

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Follow the on-screen instructions at the end (it may ask you to run two `echo` commands to add brew to your PATH).

**2. Install Python, Git, and PostgreSQL:**

```bash
brew install python git postgresql@16
```

**3. Start Postgres and make it run in the background:**

```bash
brew services start postgresql@16
```

**4. Make sure VS Code's `code` command works:** open VS Code → Cmd+Shift+P → type "Shell Command: Install 'code' command in PATH" → Enter. Now you can type `code .` to open a folder.

**5. Enable Python environment detection in VS Code:** open VS Code settings (Cmd+,) → search for `python.terminal.useEnvFile` → check the box. This ensures your venv is automatically activated in the integrated terminal.

---

## Step 1 — Get the repo onto your machine

```bash
cd ~/Documents          # or wherever you keep projects
git clone https://github.com/AggreyN/Rackner-Project.git
cd Rackner-Project
code .                  # opens the project in VS Code
```

If the repo is empty, that's fine — you're about to fill it.

---

## Step 2 — Drop in the starter skeleton

I gave you a `rackner-backend-starter` folder. Copy its contents into your repo (the folders `ingestion/`, `db/`, `api/`, `docs/`, the `requirements.txt`, `.gitignore`, and `.env.example`). Your repo should now look like:

```
Rackner-Project/
├── ingestion/        # PDF parsing + segmentation (your Weeks 2–3)
│   └── extract_pdf.py
├── db/               # database connection, models, migrations (your Weeks 4–6)
│   ├── database.py
│   ├── models.py
│   └── test_connection.py
├── api/              # FastAPI endpoints (your Week 8)
│   └── main.py
├── docs/             # this guide + the learning path
├── data/samples/     # put downloaded SAM.gov PDFs here for testing
├── tests/
├── requirements.txt
├── .gitignore
└── .env.example
```

---

## Step 3 — Create a Python virtual environment

A "venv" is an isolated box for this project's Python packages so they don't clash with anything else.

```bash
python3 -m venv venv
source venv/bin/activate     # you'll run this every time you work on the project
```

Your terminal prompt should now start with `(venv)`. 

Install the project's packages:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Step 4 — Create your database

```bash
createdb rackner
```

That makes an empty Postgres database called `rackner` on your machine.

Now set up your environment file (this holds your database address; it never gets committed to Git):

```bash
cp .env.example .env
```

The default `.env` already points at your local `rackner` database, so you don't need to change anything yet.

---

## Step 5 — The payoff: connect Python to the database

```bash
python db/test_connection.py en```

If everything worked, you'll see something like:

```
✅ Connected to PostgreSQL!
PostgreSQL 16.x ...
```

**That is your Week 1 deliverable done.** You now have the full backbone: environment, repo structure, a running database, and Python talking to it.

---

## Step 6 — Save your work to GitHub

```bash
git checkout -b setup-week1        # work on a branch, not main
git add .
git commit -m "Week 1: project scaffold + database connection"
git push -u origin setup-week1
```

Then open the repo on GitHub and you'll see a prompt to open a Pull Request. That's how your teammates review and merge your work.

---

## If you get stuck (you will, everyone does)

- **`command not found: brew`** → Homebrew isn't on your PATH yet. Close and reopen Terminal, or run the two commands Homebrew printed at the end of install.
- **`createdb: command not found`** → run `brew link postgresql@16` or restart Terminal.
- **`could not connect to server`** → Postgres isn't running: `brew services restart postgresql@16`.
- **`ModuleNotFoundError`** → your venv isn't active (`source venv/bin/activate`) or you skipped `pip install -r requirements.txt`.
- **Anything else** → copy the full error message and send it to me. Reading errors is a core skill; we'll do it together.

---

## What comes next (Week 2 preview)

Open `ingestion/extract_pdf.py`. It already has a working function that pulls text out of a PDF page-by-page using PyMuPDF. Download one solicitation PDF from https://sam.gov into `data/samples/`, then run:

```bash
python ingestion/extract_pdf.py data/samples/your-file.pdf
```

You'll see the contract's text printed with page numbers. That's a head start on Week 2 — and proof that the hard part is very doable.
