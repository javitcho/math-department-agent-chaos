Start the math agents web app backend server on localhost:5000.

Run this command to start the FastAPI backend:

```bash
cd "/Users/javiermejia/Documents/GitHub Repos/math-department-agent-chaos/math-agents" && python main.py --serve --no-open
```

While that starts, tell the user:

1. The backend will be at http://localhost:5000
2. To start the React frontend, open a second terminal and run:
   ```bash
   cd "/Users/javiermejia/Documents/GitHub Repos/math-department-agent-chaos/math-agents/web"
   npm install   # first time only
   npm run dev
   ```
3. Then open http://localhost:5173 in a browser

If the backend fails to start (e.g. port already in use or missing packages), report the error and suggest:
- `pip install fastapi uvicorn[standard]` if import fails
- `lsof -i :5000` to find what's using the port
