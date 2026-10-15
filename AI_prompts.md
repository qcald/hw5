# AI Prompts

The prompts used to build HW5 with an AI coding assistant (Claude Code), in order. Prompts that came with screenshots of the assignment are summarized in brackets. Each one has a short note on what it produced.

1. **"make a new folder for hw5"**
   Created `hw5/` with its own `.venv`.

2. **"alright data has some databses for campuscustoms shop, can you make a copy of the database file called data/campus_customs_new.db and use that for all back end things, keep the original copy if we need to reset things"**
   Copied the database to `data/campus_customs_new.db`. The original stays untouched for resets.

3. **"here are the rules for this homework. Make sure you follow them exactly"** [screenshot of the shop rules: `desk.date_today` is today, vendor lead times, no shipping with an open invoice, human approval for payments, no negative balances, cash only goes out, reset before a full run, no emailing or calling, only `gpt-6-luna` through Portkey]
   Recorded the rules for the project. They're now in the README's "Homework rules" section.

4. **"start a file output/harness.md and for each table in the db list the fields in that table and one short line about why that table matters to the agents"**
   Started `output/harness.md` with all nine tables.

5. **"write an mcp server in mcp_server/ using fast mcp. It will only talk to data/campus_customs_new.db. Don't need to connect or start it yet"**
   Created the FastMCP server.

6. **"i didn't ask you to make tools yet. Get rid of the ones you made"**
   Stripped the server back to an empty skeleton.

7. **"ok now write three tools only, we will add more later. these tools should be clearly named, add descriptions in the harness and what tickets they might help with. also add a readme for the mcp server"**
   Added `list_open_tickets`, `check_stock`, and `list_bills_due`, documented them in the harness, and wrote `mcp_server/README.md`.

8. **"ok add the mcp server to this project so that you can call the tools. save the connection JSON text in .mcp.json at the hw5 root. Then test all three of the tools and save the prompt, the tool name, and the output in output/mcp_smoke.json"**
   Created `.mcp.json`, smoke-tested the tools, and saved `output/mcp_smoke.json`.

9. **"Yes, start a new session in the hw5 folder so the campus-customs MCP server loads and you can call the tools directly."**
   Confirmed the tools work when called directly from Claude Code.

10. **"alright set up the agent team using pydanticAI. There hsould be a boss agent, inventory, accounting, facilities, and customer service. put the agent prompts in backend/prompts.md and the agent files under backend/. write detailed prompts for what each agent needs, take into account the shop rules. Create any tools in the MCP server you think the agents would need. Make sure all shop facts come from the MCP server, don't go around it or invent info. Also make sure that all agents audit to output/audit_trail.json as they run -- append don't overwrite. update the harness with descriptions of the agents and the new tools, also a short safety section. Update the readme as well"**
   Built the five-agent team, the agent tools, payment approval enforced by the server, and the append-only audit trail.

11. **"make output/desk_tickets.html with three tabs, one for each ticket. On each tab, have an "expected" section and an "actual" section. Don't fill them in yet"**

12. **"for the expected sections, write a quick paragraph on the expected workflow for each ticket. DO NOT test them, just what you think should happen. it should include who the boss calls first, any other agents the boss should call, and the tools those agents should use. You don't need to be super detailed. Just one paragraph"**

13. **"create a backend for a react frontend dashboard. In backend/main.py use FastAPI to do the following routes. List each route in the harness in one line with a brief description of it"** [screenshot: list the tickets, run a ticket, recent agent events, approve a payment (the only thing that changes cash), checking balance, reset]
    Built the FastAPI routes. Agent payments are queued, and only the approve route pays.

14. **"make sure the backend starts up with this command uvicorn main:app --reload --port 8000. You can leave both the decisions"**

15. **"build the frontend dashboard in frontend/ using react vite and typescript. It should do at minimum the things in this screenshot. I hate jira boards, make sure it doesn't look like one of those. Also make it really clean and simple to understand even for someone that doesn't have a techinical background. it's for a yale campus customs store so maybe make the ui in yale colors but don't overdo it on the yale stuff"** [screenshot: list the tickets, start a run, live agent activity, mark resolved, per-agent summary, human approval, checking balance]

16. **"can you run it"**, then **"im getting an error when trying to run a request"**
    Fixed the run error by switching to Portkey's Responses endpoint: `gpt-6-luna` doesn't allow tool calls on Chat Completions while reasoning is on.

17. **"can you make the draft messages show up a little better, i only see the intro to them and cant expand or scroll"**

18. **"also i was getting prompted for approvals before getting a full report. make sure the "where it stands" comes out first before asking for human approval"**

19. **"can you make it look a little more sophisticated and clean"**

20. **"ok write output/design.md going over the design and why we made the choices we did"**

21. **"test the agents by resetting the data and actually running the three tickets. update the desk_tickets.html actual part with what actually happened. also make a cash tab on the html to itemize the cash flows from the tickets"**
    Also: **"also save output/resolved_tickets.json for each ticket with id, final status, short outcome, what each agent did, and any human approvals"**, **"finish the harness"**, and **"finally, create a reflections tab in the html and answer these questions in two paragraphs. be detailed but don't go too crazy, it should be easy to understand"** [screenshot of the five reflection questions]
    I approved both payments on the dashboard myself; the assistant never approved anything.

22. **"once all of that is done make sure the folder has this file structure exactly."** [screenshot of the required `hw5/` layout]
    Merged the backend into `main.py` and `models.py`, split the prompts into `backend/prompts/`, and added this file, `.env.example`, `.gitignore`, the README, `output/resolved_board.html`, and `output/github_url.txt`.
