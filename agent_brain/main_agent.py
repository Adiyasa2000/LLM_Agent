import os
import sys
from dotenv import load_dotenv

# --- Tilføj rodmappen til sys.path for at finde 'tools.py' ---
# Dette er nødvendigt, hvis du kører main_agent.py direkte fra agent_brain mappen.
# Hvis du kører fra rodmappen (basin_agent/), er det teknisk set ikke nødvendigt,
# men det skader ikke at have med for robusthed.
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..'))
if project_root not in sys.path:
    sys.path.append(project_root)
# ------------------------------------------------------------

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import create_openai_tools_agent, AgentExecutor
from tools import available_tools

# --- Konfiguration ---
load_dotenv(dotenv_path=os.path.join(project_root, '.env')) # Indlæs .env fra rodmappen
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY")
LLM_MODEL           = "gpt-4o" 

# --- Initialiser LLM ---
# Temperature=0 gør outputtet mere deterministisk/forudsigeligt
llm = ChatOpenAI(model=LLM_MODEL, temperature=1, openai_api_key=OPENAI_API_KEY)

# --- Definer Agent Prompt ---
# Dette er den KRITISKE instruktion til agenten
SYSTEM_PROMPT = """
Du er en specialiseret assistent til analyse af danske regnvandsbassiner. Dit mål er at besvare brugerens spørgsmål ved hjælp af de tilgængelige værktøjer.

**VIGTIG ARBEJDSGANG:**

1.  **ALTID FØRSTE SKRIDT:** Når brugeren spørger om et specifikt bassin eller bassiner i en kommune, **skal du ALTID starte med at bruge `Basin_Match` værktøjet**. Brug brugerens input (kommune og/eller ID) til `kommune_query` og/eller `basin_id_query`.

2.  **HÅNDTER `Basin_Match` RESULTAT:**
    *   Hvis `status` er `'found_exact'`: Perfekt! Brug det returnerede `basin_identifier` og `kommune` til eventuelle efterfølgende analyseværktøjs-kald.
    *   Hvis `status` er `'found_multiple'`: **GÆT IKKE!** Præsenter beskeden fra `message_to_user` for brugeren og bed dem om at **bekræfte det præcise `basin_identifier`**, de ønsker at analysere. Brug derefter det bekræftede ID/kommune (evt. med et nyt `Basin_Match` kald for at være sikker, hvis brugeren kun gav ID'et).
    *   Hvis `status` er `'not_found'`, `'no_query'` eller `'error'`: Informer brugeren klart om resultatet og **stop** den aktuelle analyse-sekvens.

3.  **BRUG ANDRE VÆRKTØJER:** Kald KUN de andre analyseværktøjer (`Get_Basin_Attributes`, `Check_Natura2000_Overlap`, `Check_Protected_Nature`, `Check_Species_AnnexIV_Proximity`, `Check_VP3_Streams_Proximity`) **EFTER** du har fået et **eksakt** `basin_identifier` og `kommune` bekræftet via `Basin_Match`. Giv disse præcise værdier videre til værktøjet.

4.  **KORTGENERERING:** Hvis brugeren beder om et kort (typisk efter en succesfuld analyse), brug da `Generate_Basin_Map` værktøjet med det bekræftede `basin_identifier`, `kommune`, og en passende `map_scale` (brug 1000 som default). Præsenter stien til det genererede kort for brugeren.

5.  **SVAR KUN BASERET PÅ VÆRKTØJER:** Baser dine svar **udelukkende** på informationen returneret fra værktøjerne. Hvis et værktøj returnerer en fejl, så rapporter fejlen til brugeren. Vær klar og præcis.

6.  **SVAR MÅDE:** Du skal omsætte json resultater til sproglige beskrivelser
"""

# Opret prompt template
prompt = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="chat_history", optional=True), # Tilføj hukommelse hvis nødvendigt senere
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"), # Hvor agenten "tænker"
    ]
)

# --- Opret Agent ---
# Bruger OpenAI Tools Agent, som er god til at vælge værktøjer og argumenter
agent = create_openai_tools_agent(llm, available_tools, prompt)

# --- Opret Agent Executor ---
# verbose=True printer agentens tankerække og værktøjskald - VIGTIGT for debugging!
# handle_parsing_errors=True gør den mere robust hvis LLM'en returnerer mærkeligt format
agent_executor = AgentExecutor(
    agent=agent,
    tools=available_tools,
    verbose=True,
    handle_parsing_errors=True
)

# --- Interaktions-Loop ---
def run_agent_loop():
    print("\n--- Basin Analyse Agent ---")
    print("Skriv din forespørgsel, eller 'quit'/'exit' for at afslutte.")
    # Initialiser simpel chat historik (kun for denne session)
    chat_history = []

    while True:
        try:
            user_input = input("\nDu: ")
            if user_input.lower() in ["quit", "exit"]:
                print("Afslutter agent.")
                break

            # Kald agent executor med input og (evt. tom) historik
            # Agent Executor håndterer selv at tilføje til 'agent_scratchpad'
            response = agent_executor.invoke({
                "input": user_input,
                "chat_history": chat_history # Send historik med (kan være tom)
            })

            # Tilføj brugerinput og agent output til historikken for næste tur
            # Bemærk: Dette er en meget simpel hukommelse. LangChain har mere avancerede hukommelses-typer.
            # chat_history.append({"role": "user", "content": user_input})
            # chat_history.append({"role": "assistant", "content": response.get("output", "")})
            # Juster baseret på præcis hvordan `invoke` returnerer og forventer historik

            print("\nAgent:", response.get("output", "Intet svar modtaget."))

        except Exception as e:
            print(f"\nFEJL: Der opstod en uventet fejl under agent kørsel: {e}")
            # Overvej om løkken skal fortsætte eller bryde ved fejl
            # break

if __name__ == "__main__":
    run_agent_loop()