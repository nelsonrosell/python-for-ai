# SharePoint + SQL Hybrid Agent

This design is for a Python app that can answer from SharePoint documents, live SQL data, or both in the same conversation.

## Component Diagram

See [sharepoint_sql_hybrid_agent.mmd](e:/Repo/PythonProject/python-for-ai/docs/architecture/sharepoint_sql_hybrid_agent.mmd).

## When To Use Each Path

- Use `RAG` for document-heavy questions such as policies, SOPs, guides, contracts, or knowledge articles stored in SharePoint.
- Use `SQL` for exact facts such as counts, sums, filters, joins, current records, or operational reporting.
- Use `Hybrid` when the user asks a question that needs both policy/document context and live SQL facts.

Examples:

- `RAG`: "What does the onboarding policy say about late approvals?"
- `SQL`: "How many late approvals do we have this month?"
- `Hybrid`: "According to the onboarding policy, are this month's late approvals compliant?"

## Suggested Python Folder Structure

```text
project/
  app/
    __init__.py
    config.py
    main.py
    ui/
      streamlit_app.py
      chat_session.py
    agent/
      orchestrator.py
      router.py
      answer_builder.py
      models.py
    rag/
      sharepoint_client.py
      document_loader.py
      text_extractor.py
      chunking.py
      embeddings.py
      retriever.py
      citations.py
      ingestion.py
    sql/
      sql_tool.py
      sql_guardrails.py
      sql_prompt.py
      db.py
    tools/
      email_tool.py
      export_tool.py
      alert_tool.py
    auth/
      graph_auth.py
      entra_auth.py
    logging_utils.py
  docs/
    architecture/
      sharepoint_sql_hybrid_agent.md
      sharepoint_sql_hybrid_agent.mmd
  tests/
    test_router.py
    test_retriever.py
    test_sql_tool.py
    test_answer_builder.py
    test_email_tool.py
```

## Responsibilities By Layer

- `ui/streamlit_app.py`: chat input, rendering, session state, user-facing controls.
- `agent/router.py`: classify each request as `sql`, `rag`, or `hybrid`.
- `agent/orchestrator.py`: execute the selected path and coordinate multiple tools.
- `rag/sharepoint_client.py`: read files and metadata from SharePoint.
- `rag/text_extractor.py`: normalize PDF, DOCX, PPTX, XLSX, TXT, and Markdown into text.
- `rag/retriever.py`: return the most relevant chunks with metadata and citations.
- `sql/sql_tool.py`: execute validated SQL safely against the database.
- `sql/sql_guardrails.py`: block unsafe SQL and enforce allowlists.
- `agent/answer_builder.py`: combine SQL facts and retrieved documents into one grounded answer.
- `tools/email_tool.py`: optional action layer for sending results or alerts.

## Request Routing Logic

The router should classify a request into one of three intents:

- `sql`
- `rag`
- `hybrid`

The simplest safe approach is explicit rule-based routing first, with optional LLM routing later.

### Rule-Based Heuristics

Use `sql` when the prompt asks for:

- counts, totals, averages, top N, latest rows
- current operational facts
- filters by date, country, status, owner, amount
- joins or comparisons across structured fields

Use `rag` when the prompt asks for:

- what a policy, SOP, guide, or contract says
- summaries or explanations of stored documents
- comparisons between documents
- source-backed explanations from SharePoint files

Use `hybrid` when the prompt asks for:

- a policy judgment plus live data
- document guidance applied to current records
- answers requiring both supporting docs and current SQL facts

### Example Router Pseudocode

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class RouteDecision:
    mode: str  # "sql", "rag", or "hybrid"
    reason: str


SQL_TERMS = {
    "count", "sum", "average", "avg", "total", "top", "latest",
    "row", "rows", "table", "database", "sql", "filter", "group by",
}

RAG_TERMS = {
    "policy", "document", "sharepoint", "procedure", "sop", "guide",
    "manual", "contract", "what does it say", "according to the document",
}


def route_request(question: str) -> RouteDecision:
    normalized = question.lower()
    wants_sql = any(term in normalized for term in SQL_TERMS)
    wants_rag = any(term in normalized for term in RAG_TERMS)

    if wants_sql and wants_rag:
        return RouteDecision("hybrid", "contains SQL and document signals")
    if wants_sql:
        return RouteDecision("sql", "contains structured data signals")
    if wants_rag:
        return RouteDecision("rag", "contains document retrieval signals")

    return RouteDecision("rag", "default to document retrieval for ambiguous knowledge questions")
```

## Orchestration Logic

After routing, the orchestrator should behave like this:

```python
def handle_question(question: str) -> str:
    decision = route_request(question)

    if decision.mode == "sql":
        sql_result = run_sql_tool(question)
        return answer_from_sql(question, sql_result)

    if decision.mode == "rag":
        passages = retrieve_sharepoint_chunks(question)
        return answer_from_documents(question, passages)

    passages = retrieve_sharepoint_chunks(question)
    sql_result = run_sql_tool(question)
    return answer_from_hybrid_context(question, passages, sql_result)
```

## Grounding Rules

- Never use RAG to replace exact structured facts that should come from SQL.
- Never use SQL to replace policy or narrative content that lives in SharePoint documents.
- For hybrid answers, return both:
  - the SQL-backed fact
  - the SharePoint-backed evidence
- Always attach source metadata for document answers, such as file name, site, folder, and optionally page or section.

## Recommended Output Shape

For hybrid answers, structure the response in this order:

1. direct conclusion
2. SQL findings
3. SharePoint evidence
4. citations or file links

Example:

```text
Conclusion: These records appear non-compliant with the approval policy.

SQL findings:
- 18 submissions were approved after the 3-day threshold this month.

SharePoint evidence:
- The onboarding policy states approvals must be completed within 3 business days.

Sources:
- Onboarding Policy.docx, section 4.2
- SQL table: approval_events
```

## First Implementation Recommendation

Build in this order:

1. rule-based router
2. SharePoint retrieval pipeline
3. SQL tool with guardrails
4. answer builder with citations
5. optional tool actions like email/export

That keeps routing explainable and avoids overcomplicating the first version.
