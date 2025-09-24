# Orchestrator Agent Instructions: SDLC Document Generator

## 🎯 Purpose
The orchestrator agent coordinates which SDLC document is being created, attaches relevant upstream documents, and manages change policies.  
This allows the Master Prompt to remain universal and context-aware.

---

## 1. Required Inputs to Each LLM Call
When invoking the Master Prompt, always pass:

- **`current_doc_type`** → The document type being generated (e.g., "BRD", "SRS", "Test Plan").  
- **`attachments`** → All relevant prior documents (Markdown versions).  
- **`doc_registry`** → IDs + versions of existing docs. Example:  
  ```json
  {
    "Project Charter": "v1.0",
    "BRD": "v1.3",
    "SRS": "v1.1"
  }
  ```
- **`allow_upstream_edits`** → `true` / `false`.  
- **`change_policy`** → `auto` | `review` | `none`. (Default = `review`)

### Baseline Templates
- Some document types (e.g., **Code Standards & Guidelines**, **Design Guidelines**, **Security Policies**) 
  rely on baseline `.md` templates instead of being generated from scratch.  
- If a baseline `.md` file exists, the orchestrator must **attach it** in the `attachments` list.  
- The assistant will then **import the template as the starting point** and only prompt the user for 
  project-specific changes or additions.  
- If no baseline is provided, the assistant will generate a best-practice default and recommend saving it 
  as a template for future projects.

---

## 2. Orchestrator Responsibilities
1. **Guide Document Flow**  
   - Decide which doc is next.  
   - Provide prior docs as attachments for reuse.  
   - Pass correct `current_doc_type`.  

2. **Attach Prior Docs & Templates**  
   - Always attach the most recent **Markdown versions** of upstream docs.  
   - Attach **baseline templates** if the doc type depends on them.  
   - Attach multiple docs if needed for context (e.g., SRS + Personas when generating Stories).  

3. **Manage Change Propagation**  
   - If downstream info conflicts upstream:  
     - With `auto`: let assistant apply patches automatically.  
     - With `review`: assistant generates a Patch Plan, you approve or reject.  
     - With `none`: assistant logs deviation, no upstream edit.  

4. **Capture Outputs**  
   - Store returned **PDF + Markdown**.  
   - For backlog: also capture **JIRA CSV + JSON**.  
   - Update your `doc_registry` with new versions.  

---

## 3. Change Policy Modes
- **auto** → Assistant updates upstream docs, increments version, cascades changes automatically.  
- **review** (default) → Assistant proposes Patch Plan, orchestrator must approve/reject.  
- **none** → No upstream changes. Assistant logs a deviation in current doc + changelog.  

---

## 4. Example Call (Generating Code Standards)
```json
{
  "current_doc_type": "Code Standards & Guidelines",
  "attachments": ["Code_Standards_Baseline.md"],
  "doc_registry": {
    "Project Charter": "v1.0",
    "BRD": "v1.3"
  },
  "allow_upstream_edits": true,
  "change_policy": "review"
}
```

---

## 5. Best Practices for Orchestrator
- Always pass the **minimum set of prior docs** needed for context.  
- Default to `review` mode to maintain human oversight.  
- Keep `doc_registry` updated after every call.  
- For Backlog generation, ensure **SRS + Personas** are attached.  
- Store **ChangeLogs** alongside document versions for full audit trail.  
- Attach **baseline templates** when generating standards or guidelines docs.  

---

## ✅ End State
By following these rules, the orchestrator ensures:  
- Each doc builds on prior work or templates.  
- Conflicts are caught and resolved consistently.  
- Outputs are versioned, traceable, and ready for client + engineering use.
