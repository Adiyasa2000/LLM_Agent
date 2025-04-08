import streamlit as st
import os
import re
from pathlib import Path

# LangChain/OpenAI Imports
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from langchain.agents import create_openai_tools_agent, AgentExecutor

# Import local tools
from tools import available_tools # Sørg for at tools.py er opdateret med exists() tjek!

# --- Konfiguration & Initialisering ---
load_dotenv(dotenv_path='.env')
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_MODEL = "gpt-4o"

if not OPENAI_API_KEY:
    st.error("Fejl: OPENAI_API_KEY mangler.", icon="🚨")
    st.stop()

# Initialiser LLM, Prompt, Agent, Executor (kun én gang)
@st.cache_resource # Cache executor for bedre ydeevne
def get_agent_executor():
    llm = ChatOpenAI(model=LLM_MODEL, temperature=0.8, openai_api_key=OPENAI_API_KEY)
    SYSTEM_PROMPT = """
Du er en specialiseret assistent til analyse af danske regnvandsbassiner. Dit mål er at besvare brugerens spørgsmål ved hjælp af de tilgængelige værktøjer. Svar altid på dansk.

**VIGTIG ARBEJDSGANG:**

1.  **ALTID FØRSTE SKRIDT:** Brug ALTID `Basin_Match` værktøjet FØRST for at validere kommune/bassin ID.
2.  **HÅNDTER `Basin_Match` RESULTAT:** Spørg brugeren hvis flere matches findes. Stop hvis intet findes.
3.  **BRUG ANDRE VÆRKTØJER:** Brug KUN andre analyseværktøjer (`Get_Basin_Attributes`, etc.) EFTER et eksakt match er fundet, og KUN hvis relevant for spørgsmålet.
4.  **KORT/PDF GENERERING:** Brug KUN `Generate_Basin_Map` / `Generate_Simple_Report` hvis brugeren specifikt beder om det EFTER en analyse. Værktøjet returnerer enten præcis strengen "Fil gemt her: [relativ_sti]" eller en fejlbesked. **Gentag KUN værktøjets output direkte uden ekstra tekst eller formatering.**
5.  **SVAR BASERET PÅ VÆRKTØJER:** Baser svar UDELUKKENDE på værktøjsoutput. Omsæt JSON til letforståelig tekst. **Når et værktøj returnerer en filsti via "Fil gemt her: ...", gentag den streng og KUN den streng.**
"""
    prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
    agent = create_openai_tools_agent(llm, available_tools, prompt)
    agent_executor = AgentExecutor(
        agent=agent, tools=available_tools, verbose=False, handle_parsing_errors=True
    )
    return agent_executor

agent_executor = get_agent_executor()

# --- Streamlit App UI ---

st.title("💧 Basin Analyse Agent")
st.caption("Analyser danske regnvandsbassiner")

# Initialiser chat historik
if "messages" not in st.session_state:
    st.session_state.messages = [
        AIMessage(content="Hej! Angiv kommune og/eller bassin ID jeg skal undersøge.")
    ]

# Funktion til at vise svar og håndtere fil-links (UDEN DEBUG, MED PÆNERE TEKST)
def display_response_with_links(response_text):
    # Find sti efter "Fil gemt her: "
    path_match = re.search(r"Fil gemt her:\s*(results[\\/][^ ]+\.(?:png|pdf))", response_text, re.IGNORECASE)

    if path_match:
        relative_path_str = path_match.group(1).replace("\\", "/")
        app_dir = Path(__file__).parent
        full_path = app_dir / relative_path_str

        # Tjek om filen rent faktisk findes
        if full_path.exists() and full_path.is_file():
            file_name = full_path.name
            file_type = "Kortet" if full_path.suffix.lower() == ".png" else "PDF Rapporten"

            # --- PÆNERE BESKED HER ---
            st.write(f"{file_type} for bassinet er nu klar.")
            # --- SLUT PÆNERE BESKED ---

            try:
                # Download Button
                with open(full_path, "rb") as fp:
                    st.download_button(
                        label=f"Download {file_name}", data=fp, file_name=file_name
                    )
                # Vis billede hvis PNG
                if full_path.suffix.lower() == ".png":
                    st.image(str(full_path))
            except Exception as e:
                st.error(f"Fejl ved håndtering af fil {file_name}: {e}")
        else:
            # Fil blev ikke fundet trods match - vis den originale besked (som nu bør være en fejl fra værktøjet)
            st.write(f"Problem: Kunne ikke finde den genererede fil ({relative_path_str}). Værktøjet returnerede: {response_text}")

    else:
        # Ingen "Fil gemt her:" fundet, vis bare den originale tekst
        st.write(response_text)

# Vis chat historik
for message in st.session_state.messages:
    avatar = "👤" if isinstance(message, HumanMessage) else "🤖"
    with st.chat_message(message.type, avatar=avatar):
        if isinstance(message.content, str):
            display_response_with_links(message.content)
        elif message.content is not None:
             st.write(str(message.content)) # Fallback

# Håndter nyt brugerinput
if user_input := st.chat_input("Din besked..."):
    st.session_state.messages.append(HumanMessage(content=user_input))

    with st.spinner("Analyserer..."):
        try:
            response = agent_executor.invoke({
                "input": user_input,
                "chat_history": st.session_state.messages[:-1]
            })
            agent_response_text = response.get("output", "Kunne ikke få svar fra agent.")
            st.session_state.messages.append(AIMessage(content=agent_response_text))

        except Exception as e:
            error_message = f"Systemfejl under analyse: {type(e).__name__}: {e}"
            st.error(error_message)
            st.session_state.messages.append(AIMessage(content=error_message))

    # Gentegn UI for at vise nyeste beskeder
    st.rerun()