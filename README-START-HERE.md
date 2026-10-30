# AI Clip Studio: GitHub migration-ready source

Upload the `ai-clip-studio/` folder and root `.dockerignore` to a *new* GitHub repository under your connected GitHub account. This ZIP is a source backup, **not** the live deployed website.

Existing Render service Docker setup should remain:
- Docker runtime
- Dockerfile path: `ai-clip-studio/Dockerfile`
- Docker context: `.`
- Branch: `main` (or whichever branch exists in the new repository)

Read `ai-clip-studio/README-RESTORE-TH.md` for tests and limitations. No API keys are included.
