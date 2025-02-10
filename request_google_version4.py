import json
import requests
from bs4 import BeautifulSoup
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from urllib.parse import urlparse, parse_qs
import os
from datetime import datetime
import re

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


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


def main():
    termo_pesquisa = "Fábio Gabriel Araújo Salvador + crime OR lavagem OR sonegacao OR corrupcao OR desvio OR cartel OR doleiro OR operacao OR policia OR preso OR condenado OR ilicito OR prostituicao OR esquema OR trafico OR arm-absolve"
    num_links = 100  # Número de links
    caminho_desktop = os.path.join(os.path.join(os.environ["USERPROFILE"]), "Desktop")

    diretorio_saida = os.path.join(caminho_desktop, "output")
    if not os.path.exists(diretorio_saida):
        os.makedirs(diretorio_saida)

    all_links = set()
    start = 0

    while len(all_links) < num_links:
        html_resultados = obter_resultados_pesquisa_google(termo_pesquisa, start=start)

        if html_resultados:
            links = parsear_html_resultados_pesquisa(
                html_resultados, num_links - len(all_links)
            )
            all_links.update(links)
            print(f"Total de links obtidos até agora: {len(all_links)}")
        else:
            break

        start += 10

    all_links = list(all_links)[:num_links]

    artigos = extrair_conteudo_links(all_links)
    print("=" * 50)
    for artigo in artigos:
        print(f"Link: {artigo['link']}")
        print(f"Conteúdo: {artigo['conteudo']}")
        print("=" * 50)

    json_saida = {
        "Consulta": termo_pesquisa,
        "Data de Pesquisa": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    for idx, artigo in enumerate(artigos, 1):
        json_saida[f"link{idx}"] = {"link": artigo["link"], "texto": artigo["conteudo"]}

    arquivo_saida = os.path.join(diretorio_saida, "output.json")
    with open(arquivo_saida, "w", encoding="utf-8") as f:
        json.dump(json_saida, f, ensure_ascii=False, indent=4)

    print(f"JSON gerado com sucesso e salvo em '{arquivo_saida}'.")


if __name__ == "__main__":
    main()
