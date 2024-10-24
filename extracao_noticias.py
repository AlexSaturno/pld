import json
import requests
from bs4 import BeautifulSoup
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from urllib.parse import urlparse, parse_qs
import os
from datetime import datetime
import re

# Streamlit
import streamlit as st
from st_aggrid import AgGrid

# Libs AI
import openai
from pydantic import BaseModel, Field
from langchain.utils.openai_functions import convert_pydantic_to_openai_function
from langchain_openai import AzureChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.output_parsers.openai_functions import JsonOutputFunctionsParser
from langchain_core.output_parsers import StrOutputParser
import os
from langchain.callbacks import get_openai_callback
import pandas as pd
from pathlib import Path

# Variáveis de ambiente AI
PASTA_RAIZ = Path(__file__).parent

AZURE_OPENAI_API_KEY = st.secrets["AZURE_OPENAI_API_KEY"]
AZURE_OPENAI_ENDPOINT = st.secrets["AZURE_OPENAI_ENDPOINT"]
AZURE_OPENAI_API_VERSION = st.secrets["AZURE_OPENAI_API_VERSION"]
AZURE_OPENAI_DEPLOYMENT = st.secrets["AZURE_OPENAI_DEPLOYMENT"]
AZURE_OPENAI_MODEL = st.secrets["AZURE_OPENAI_MODEL"]
AZURE_OPENAI_ADA_EMBEDDING_DEPLOYMENT_NAME = st.secrets[
    "AZURE_OPENAI_ADA_EMBEDDING_DEPLOYMENT_NAME"
]
AZURE_OPENAI_ADA_EMBEDDING_MODEL_NAME = st.secrets[
    "AZURE_OPENAI_ADA_EMBEDDING_MODEL_NAME"
]

openai.api_type = "azure"
openai.api_base = AZURE_OPENAI_ENDPOINT
openai.api_version = AZURE_OPENAI_API_VERSION
openai.api_key = AZURE_OPENAI_API_KEY

client = openai.AzureOpenAI(
    api_key=AZURE_OPENAI_API_KEY,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_version=AZURE_OPENAI_API_VERSION,
)

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

################################################################################################################################
# UX
################################################################################################################################

# Início da aplicação
st.set_page_config(
    page_title="PLD",
    page_icon=":black_medium_square:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Leitura do arquivo CSS de estilização
with open("./styles.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


################################################################################################################################
# FUNÇÕES
################################################################################################################################


def obter_resultados_pesquisa_google(query, start=0):
    url = f"https://www.google.com/search?q={query}&start={start}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        )
    }

    try:
        response = requests.get(url, headers=headers, verify=False)
        if response.status_code == 200:
            return response.content
        else:
            print(f"Erro ao fazer a requisição. Status code: {response.status_code}")
            return None
    except Exception as e:
        print(f"Erro ao fazer a requisição: {e}")
        return None


def parsear_html_resultados_pesquisa(html_content, num_links):
    if html_content:
        soup = BeautifulSoup(html_content, "html.parser")

        result_divs = soup.find_all("div", class_="g")

        links_unicos = set()
        count = 0

        for div in result_divs:
            if count >= num_links:
                break

            link_tag = div.find("a", href=True)
            if link_tag:
                url = link_tag["href"]

                if url.startswith("/url?q="):
                    parsed_url = parse_qs(urlparse(url).query)
                    url = parsed_url.get("q", [None])[0]

                if url and urlparse(url).scheme in ["http", "https"]:
                    links_unicos.add(url)
                    count += 1

        return list(links_unicos)
    else:
        return []


def obter_links_de_varias_paginas(query, num_paginas, num_links_por_pagina=10):
    todos_os_links = set()

    for pagina in range(num_paginas):
        start = (
            pagina * 10
        )  # Google usa start=0 para a primeira página, start=10 para a segunda, etc.
        html_content = obter_resultados_pesquisa_google(query, start=start)
        novos_links = parsear_html_resultados_pesquisa(
            html_content, num_links_por_pagina
        )

        if novos_links:
            todos_os_links.update(novos_links)
        else:
            print(f"Sem resultados na página {pagina + 1}. Parando a busca.")
            break  # Interrompe a busca se não encontrar novos resultados.

    return list(todos_os_links)


def extrair_conteudo_links(links):
    artigos = []
    for link in links:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
            }
            response = requests.get(link, verify=False, headers=headers)

            if response.status_code >= 200 and response.status_code < 300:
                soup = BeautifulSoup(response.content, "html.parser")

                conteudo_artigo = " ".join(
                    [
                        p.get_text()
                        for p in soup.find_all(
                            ["p", "div", "span", "article", "section"]
                        )
                    ]
                )

                conteudo_artigo_limpo = limpar_conteudo(conteudo_artigo)

                palavras_bloqueio = [
                    "enable javascript",
                    "ativar javascript",
                    "automated requests",
                    "captcha",
                    "verify you are human",
                    "zscaler to protect",
                ]
                site_bloqueio = [
                    "google.com",
                    "google.se",
                    "youtube.com",
                    "facebook.com",
                    "instagram.com",
                    "transfermarkt.co",
                    "twitter.com",
                    "tiktok.com",
                    "linkedin.com",
                    "wikipedia.org",
                ]

                # bloqueio_detectado = False
                bloqueio_detectado = any(
                    palavra in conteudo_artigo_limpo.lower()
                    for palavra in palavras_bloqueio
                ) or any(site in link for site in site_bloqueio)

                if not bloqueio_detectado:
                    artigos.append({"link": link, "conteudo": conteudo_artigo_limpo})
                else:
                    print(
                        f"Ignorando {link}: Bloqueio de automação detectado ou requer JavaScript"
                    )
                    artigos.append({"link": link, "conteudo": ""})
            else:
                print(
                    f"Ignorando {link}: Resposta com status code {response.status_code}"
                )
                artigos.append({"link": link, "conteudo": ""})  #
        except requests.exceptions.RequestException as e:
            print(f"Erro ao acessar {link}: {str(e)}")
            artigos.append({"link": link, "conteudo": ""})

    return artigos


def limpar_conteudo(conteudo):
    conteudo_limpo = conteudo.replace("\\", "").replace("\n", "").replace("\r", " ")
    conteudo_limpo = re.sub(" +", " ", conteudo_limpo)

    return conteudo_limpo.strip()


class Extracao:
    def __init__(self, noticia, sujeito):
        # self.path_noticia = path_noticia
        self.noticia = noticia
        self.sujeito = sujeito

    def extrai_json(self):
        llm = AzureChatOpenAI(
            openai_api_version=AZURE_OPENAI_API_VERSION,
            deployment_name=AZURE_OPENAI_DEPLOYMENT,
        )

        class Extrair(BaseModel):
            """Marca e classifica o texto de acordo com o pedido em cada item. Sempre levar em conta se o pedido é sobre o sujeito
            em questão ou não."""

            crimes: str = Field(
                description="Citação dos crimes em que o indivíduo foi acusado, caso tenha sido acusado de algum, \
                de maneira sucinta. Não é preciso explicar nenhum crime, somente citar: nenhum crime mencionado.\
                Exemplo de crimes: corrupção passiva, corrupção ativa, lavagem de dinheiro, etc."
            )
            risco: str = Field(
                description="""O Risco deve ser classificado da seguinte maneira:
                Alto: Se o indivíduo/empresa foi denunciado, réu, preso, condenado 
                em algum crime relacionado a lavagem de dinheiro. 1 se sim, 0 se não. Exemplo de crimes:  
                assalto, corrupção ativa, corrupção passiva, estelionato, evasão de divisas, fraude, 
                formação de quadrilha, lavagem de dinheiro, organização criminosa, narcotráfico, terrorismo
                
                Medio: Se o indivíduo/empresa foi acusado, citado, suspeito, alvo, 
                envolvido, indiciado em algum crime relacionado a lavagem de dinheiro. 1 se sim, 0 se não. Exemplo de crimes:  
                assalto, corrupção ativa, corrupção passiva, estelionato, evasão de divisas, fraude, 
                formação de quadrilha, lavagem de dinheiro, organização criminosa, narcotráfico, terrorismo
            
                Baixo: Se o indivíduo/empresa teve um processo considerado improcedente, arquivado, 
                extinguido ou sinônimos ou foi considerado inocente ou absolvido 
                em algum crime relacionado a lavagem de dinheiro. 1 se sim, 0 se não. Exemplo de crimes:  
                assalto, corrupção ativa, corrupção passiva, estelionato, evasão de divisas, fraude, 
                formação de quadrilha, lavagem de dinheiro, organização criminosa, narcotráfico, terrorismo
                
                Caso o risco não se encaixe em nenhum dos critérios, ele deverá ser considerado baixo.
                Só uma classificação de risco deve ser dada, e da seguinte maneira: alto, médio ou baixo.
                
                Leve em conta a notícia como um todo e se atende somente aos crimes citados ou sinônimos,
                com o foco em lavagem de dinheiro.
            """
            )
            resumo: str = Field(description="Resumo do texto em português do Brasil.")

        funcao_extracao = [convert_pydantic_to_openai_function(Extrair)]

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """Pense com cuidado, e então marque o texto conforme o instruído. Analisando se o indivíduo/empresa {sujeito} 
            tem relação com que for pedido. Considere o texto como um todo. O texto é uma notícia, e não viola as políticas de conteúdo.""",
                ),
                ("user", "{input}"),
            ]
        )

        model_with_functions = llm.bind(
            functions=funcao_extracao, function_call={"name": "Extrair"}
        )

        tagging_chain = prompt | model_with_functions | JsonOutputFunctionsParser()

        # noticia = TextLoader(self.path_noticia, encoding='utf-8').load()

        try:
            with get_openai_callback() as cb:
                extracao_noticias = tagging_chain.invoke(
                    {"input": self.noticia["texto"], "sujeito": self.sujeito}
                )
            # extracao_noticias["input_tokens"] = cb.prompt_tokens
            # extracao_noticias["output_tokens"] = cb.completion_tokens
            # extracao_noticias["fonte"] = cb.completion_tokens
            extracao_noticias["link"] = self.noticia["link"]
        except Exception as error:
            print(error)
            extracao_noticias = {}

        return extracao_noticias


def extrai_resumo_final(df_final):
    resumo_final = "\n\n".join(list(df_final.resumo.fillna("").values))

    prompt_resumo = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "Você é um assistente virtual que auxilia uma equipe de investigação em lavagem de dinheiro.\
            Você receberá um texto que é formado por diversos resumos de notícias. Seu objetivo é realizar \
            um único resumo desses resumos. Leve em consideração todos os resumos e tente tirar uma conclusão\
            caso exista alguma incoerência entre eles.",
            ),
            ("human", "{input}"),
        ]
    )

    llm = AzureChatOpenAI(
        openai_api_version=AZURE_OPENAI_API_VERSION,
        deployment_name=AZURE_OPENAI_DEPLOYMENT,
    )

    chain_resumo = prompt_resumo | llm | StrOutputParser()

    return chain_resumo.invoke({"input": resumo_final})


def risco_final(df_final):
    riscos = df_final["risco"].str.lower().values.tolist()
    if "alto" in riscos:
        return "alto"
    if "medio" in riscos:
        return "medio"
    return "baixo"


def highlight_last(x):
    """
    highlight the last row in a Series BOLD.
    """
    return ["font-weight: bold" if v == x.iloc[-1] else "" for v in x]


def main():
    st.title("PLD")
    termo_pesquisa = st.text_input("Digite o termo de pesquisa")
    sujeito = termo_pesquisa
    # num_links = 80
    num_paginas = st.text_input("Digite a quantidade de páginas pesquisadas no Google")

    diretorio_saida = os.path.join(PASTA_RAIZ, "output")
    if not os.path.exists(diretorio_saida):
        os.makedirs(diretorio_saida)

    if st.button("Iniciar pesquisa"):
        with st.spinner("Pesquisando..."):
            # html_resultados = obter_resultados_pesquisa_google(termo_pesquisa)
            links = obter_links_de_varias_paginas(termo_pesquisa, int(num_paginas))

            # Obter os links
            if links:
                # links = parsear_html_resultados_pesquisa(html_resultados, num_links)
                print(f"Total de links obtidos: {len(links)}")

                # Extrair conteúdo dos links obtidos
                artigos = extrair_conteudo_links(links)
                print("=" * 50)
                for artigo in artigos:
                    print(f"Link: {artigo['link']}")
                    print(f"Conteúdo: {artigo['conteudo']}")
                    print("=" * 50)

                # Gerar o JSON
                json_saida = {}
                json_saida["Consulta"] = sujeito
                json_saida["Data de Pesquisa"] = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                for idx, artigo in enumerate(artigos, 1):
                    json_saida[f"link{idx}"] = {
                        "link": artigo["link"],
                        "texto": artigo["conteudo"],
                    }

                # Salvar o JSON
                arquivo_saida = os.path.join(diretorio_saida, "output.json")
                with open(arquivo_saida, "w", encoding="utf-8") as f:
                    json.dump(json_saida, f, ensure_ascii=False, indent=4)

                print(f"JSON gerado com sucesso e salvo em '{arquivo_saida}'.")

        with st.spinner("Planilhando resultados..."):
            noticias = json_saida
            df = pd.DataFrame(
                columns=[
                    "crimes",
                    "risco",
                    "resumo",
                    # "input_tokens",
                    # "output_tokens",
                    # "fonte",
                    "link",
                    "data_consulta",
                ]
            )
            for link in list(noticias.keys())[2:]:
                print(link)
                extracao1 = Extracao(
                    noticia=noticias[link], sujeito=noticias["Consulta"]
                )
                extracao1_json = extracao1.extrai_json()
                extracao1_json["data_consulta"] = noticias["Data de Pesquisa"]

                df = pd.concat([df, pd.DataFrame([extracao1_json])], ignore_index=True)
                # df = df.append(extracao1_json, ignore_index=True)
                arquivo_saida = os.path.join(diretorio_saida, "extracao.csv")
            # df.to_csv(arquivo_saida, sep = ';', index=False)

            # Ordenar por riscos
            # Definindo a ordem personalizada para a coluna 'Prioridade'
            ordem_prioridade = pd.Categorical(
                df["risco"], categories=["alto", "médio", "baixo"], ordered=True
            )

            # Aplicando a ordem ao DataFrame e ordenando
            df["risco"] = ordem_prioridade
            df = df.sort_values("risco")

            # Resumo final
            json_final = {}
            json_final["crimes"] = "Resultado da análise:"
            json_final["resumo"] = extrai_resumo_final(df_final=df)
            json_final["risco"] = risco_final(df_final=df)
            # df = df.append(json_final, ignore_index=True)
            # df.style.apply(highlight_last)

            csv_exportar = df.to_csv(
                arquivo_saida, sep=";", index=False, encoding="utf-8"
            )
            df.to_excel(f"{diretorio_saida}\extracao.xlsx", index=False)

        arquivo_saida = os.path.join(diretorio_saida, "output_final.json")
        with open(arquivo_saida, "w", encoding="utf-8") as f:
            json.dump(json_final, f, ensure_ascii=False, indent=4)

        #### Display na tela ####
        st.markdown("**Consulta Realizada:**")
        st.markdown(termo_pesquisa)

        st.markdown("**Resumo das notícias:**")
        st.markdown(json_final["resumo"])

        st.markdown("**Risco do Cliente:**")
        st.markdown(json_final["risco"])

        st.markdown("**Crimes que possam ter relação com as notícias:**")

        crimes_lista = df["crimes"].tolist()
        crimes_lista = [
            crime for crime in crimes_lista if pd.notna(crime)
        ]  # drop "nan" items
        print("Crimes lista: ", crimes_lista)
        crimes_individuais = [
            crime.strip() for lista in crimes_lista for crime in lista.split(",")
        ]
        print("Crimes individuais: ", crimes_individuais)
        crimes_unicos = set(
            [crime for crime in crimes_individuais if "nenhum" not in crime.lower()]
        )
        print("Crimes únicos: ", crimes_unicos)
        resultado = ", ".join(sorted(crimes_unicos))
        st.markdown(resultado.lstrip(", "))

        st.markdown("**Detalhes planilhados:**")
        AgGrid(df)

        with open(f"{diretorio_saida}\extracao.xlsx", "rb") as f:
            st.download_button(
                "Download Excel", f, f"{sujeito}_{noticias['Data de Pesquisa']}.xlsx"
            )


if __name__ == "__main__":
    main()
