import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import create_openai_tools_agent, AgentExecutor
from tools import available_tools

# --- Konfiguration ---
load_dotenv(dotenv_path='.env') # Indlæs .env fra rodmappen
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY")
LLM_MODEL           = "gpt-4o" 

# --- Initialiser LLM ---
# Temperature=0 gør outputtet mere deterministisk/forudsigeligt
llm = ChatOpenAI(model=LLM_MODEL, temperature=1, openai_api_key=OPENAI_API_KEY)

# --- Definer Agent Prompt ---
# Dette er den KRITISKE instruktion til agenten
SYSTEM_PROMPT = """
Du er en specialiseret assistent til analyse af danske regnvandsbassiner. Dit mål er at besvare brugerens spørgsmål ved hjælp af de tilgængelige værktøjer. Svar altid på dansk.

**VIGTIG ARBEJDSGANG:**

1.  **ALTID FØRSTE SKRIDT:** Brug ALTID `Basin_Match` værktøjet FØRST for at validere kommune/bassin ID.
2.  **HÅNDTER `Basin_Match` RESULTAT:** Spørg brugeren hvis flere matches findes. Stop hvis intet findes.
3.  **BRUG ANDRE VÆRKTØJER:** Brug KUN andre analyseværktøjer (`Get_Basin_Attributes`, etc.) EFTER et eksakt match er fundet, og KUN hvis relevant for spørgsmålet.
4.  **KORT/PDF GENERERING:** Brug KUN `Generate_Basin_Map` / `Generate_Simple_Report` hvis brugeren specifikt beder om det EFTER en analyse. Værktøjet returnerer enten præcis strengen "Fil gemt her: [relativ_sti]" eller en fejlbesked. **Gentag KUN værktøjets output direkte uden ekstra tekst eller formatering (ingen links, ingen ekstra sætninger).**
5.  **SVAR BASERET PÅ VÆRKTØJER:** Baser svar UDELUKKENDE på værktøjsoutput. Omsæt JSON til letforståelig tekst. **Når et værktøj returnerer en filsti via "Fil gemt her: ...", gentag den streng og KUN den streng.**
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