# InsightForge Web

The Web workspace uses the existing InsightForge agent loop and JSONL event stream. It does not implement workflow decisions in the browser.

From the `InsightForge` repository root, create the private local agent configuration once:

```bash
cp configs/agent.example.yaml configs/agent.local.yaml
```

```bash
cd web
npm install
npm run dev
```

Or from the repository root:

```bash
./insightforge web
```

The default address is `http://127.0.0.1:4173`. Override it with `INSIGHTFORGE_WEB_HOST` and `INSIGHTFORGE_WEB_PORT`.

Production mode:

```bash
cd web
npm run build
cd ..
./insightforge web start
```

Agent credentials continue to come from InsightForge environment variables or `configs/agent.local.yaml`.
