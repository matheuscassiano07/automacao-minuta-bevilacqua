# 1. Usa uma versão leve do Linux com Python já instalado
FROM python:3.10-slim

# 2. Configurações para não travar a instalação pedindo "Yes/No"
ENV DEBIAN_FRONTEND=noninteractive

# 3. Instala o LaTeX (Apenas os pacotes essenciais para não ficar pesado)
RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-latex-base \
    texlive-fonts-recommended \
    texlive-latex-extra \
    texlive-lang-portuguese \
    && rm -rf /var/lib/apt/lists/*

# 4. Cria uma pasta chamada /app dentro do servidor e entra nela
WORKDIR /app

# 5. Copia todos os seus arquivos (app.py, templates, imagens) para o servidor
COPY . /app

# 6. Instala as bibliotecas do Python listadas no requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 7. Libera a porta 10000 para a internet acessar
EXPOSE 10000

# 8. Comando final: Liga o servidor Gunicorn para rodar o Flask
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--timeout", "90", "app:app"]