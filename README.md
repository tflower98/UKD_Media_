# UK Defence Media Map

   A curated dataset of UK defence journalists with nightly article tracking and job-move flagging.

   ## What's in here

   - `data/journalists.json` — 37+ records of UK defence journalists, outlets, beats, and recent articles
   - `update_articles.py` — Nightly script that pulls Google News RSS per journalist and flags possible job moves
   - `.github/workflows/nightly.yml` — GitHub Actions workflow that runs the updater automatically

   ## How it works

   Every night at 02:15 UTC, the script:
   1. Queries Google News for recent articles under each journalist's byline
   2. Stores the five most recent articles on their record
   3. Flags if the last two bylines came from a non-home domain (possible job move)
   4. Commits the updated JSON to the repo if anything changed

   Flags wait for human review — the script never rewrites the outlet field itself.

   ## To update records

   1. Click on `data/journalists.json` in the repo
   2. Click the pencil ✎ icon to edit
   3. Make your changes
   4. Scroll down and click "Commit changes"

   ## Running the updater manually

   Go to the **Actions** tab → click **Nightly media map update** → click **Run workflow** → wait 30-60 seconds.

   ---

   Last updated: 2026-07-16
