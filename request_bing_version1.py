import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
import os
from datetime import datetime
import re
import time
import urllib3
import logging

# Configuração do logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Suprime avisos de requisições sem verificação SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def obter_links_de_varias_paginas(query, num_paginas, num_links_por_pagina=10):
    todos_os_links = set()
    session = requests.Session()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    logging.info(f"Iniciando pesquisa no Bing: {query}")

    for pagina in range(num_paginas):
        start = pagina * 10
        url = f"https://www.bing.com/search?q={query}&first={start}&count={num_links_por_pagina}&setlang=pt-br&cc=BR&mkt=pt-BR"

        try:
            time.sleep(2)
            response = session.get(url, headers=headers, verify=False, timeout=10)
            if response.status_code == 200:
                novos_links = parsear_html_resultados_pesquisa(
                    response.content, num_links_por_pagina
                )

                if novos_links:
                    todos_os_links.update(novos_links)
                else:
                    logging.warning(
                        f"Sem resultados na página {pagina + 1}. Encerrando busca"
                    )
                    break
            else:
                logging.error(
                    f"Erro ao buscar no Bing. Status code: {response.status_code}"
                )
                break
        except Exception as e:
            logging.error(f"Erro ao acessar Bing: {e}")
            break

    logging.info(f"Pesquisa concluída. Total de links extraídos: {len(todos_os_links)}")
    return list(todos_os_links)


def parsear_html_resultados_pesquisa(html_content, num_links):
    if html_content:
        soup = BeautifulSoup(html_content, "html.parser")
        links_unicos = set()
        count = 0

        result_divs = soup.find_all("li", class_="b_algo")

        for div in result_divs:
            if count >= num_links:
                break

            link_tag = div.find("a", href=True)
            if link_tag:
                url = link_tag["href"]

                if urlparse(url).scheme in ["http", "https"]:
                    links_unicos.add(url)
                    count += 1

        return list(links_unicos)
    else:
        return []


def extrair_conteudo_links(links):
    artigos = []
    palavras_bloqueio = [
        "enable javascript",
        "ativar javascript",
        "automated requests",
        "captcha",
        "verify you are human",
        "zscaler to protect",
    ]
    sites_bloqueio = [
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

    for link in links:
        if any(site in link for site in sites_bloqueio):
            continue

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            time.sleep(2)
            response = requests.get(link, verify=False, headers=headers, timeout=10)

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

                if any(
                    palavra in conteudo_artigo_limpo.lower()
                    for palavra in palavras_bloqueio
                ):
                    continue

                artigos.append({"link": link, "conteudo": conteudo_artigo_limpo})
            else:
                artigos.append({"link": link, "conteudo": ""})
        except requests.exceptions.RequestException as e:
            artigos.append({"link": link, "conteudo": ""})

    return artigos


def limpar_conteudo(conteudo):
    conteudo_limpo = conteudo.replace("\\", "").replace("\n", "").replace("\r", " ")
    conteudo_limpo = re.sub(" +", " ", conteudo_limpo)
    return conteudo_limpo.strip()


def main():
    termo_pesquisa = "Fábio Gabriel Araújo Salvador + crime OR lavagem OR sonegacao OR corrupcao OR desvio OR cartel OR doleiro OR operacao OR policia OR preso OR condenado OR ilicito OR prostituicao OR esquema OR trafico OR arm-absolve"
    num_paginas = 5  # Número de páginas
    caminho_desktop = os.path.join(os.path.join(os.path.expanduser("~")), "Desktop")
    diretorio_saida = os.path.join(caminho_desktop, "output")

    if not os.path.exists(diretorio_saida):
        os.makedirs(diretorio_saida)

    all_links = obter_links_de_varias_paginas(termo_pesquisa, int(num_paginas))
    artigos = extrair_conteudo_links(all_links)

    json_saida = {
        "Consulta": termo_pesquisa,
        "Data de pesquisa": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    for idx, artigo in enumerate(artigos, 1):
        json_saida[f"link{idx}"] = {"link": artigo["link"], "texto": artigo["conteudo"]}

    # Salvar o JSON
    arquivo_saida = os.path.join(diretorio_saida, "output.json")
    with open(arquivo_saida, "w", encoding="utf-8") as f:
        json.dump(json_saida, f, ensure_ascii=False, indent=4)

    logging.info(f"JSON gerado com sucesso e salvo em '{arquivo_saida}'.")


if __name__ == "__main__":
    main()
