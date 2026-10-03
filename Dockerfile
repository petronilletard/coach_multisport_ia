# Je pars d'une boîte qui contient déjà Python
FROM python:3.12-slim

# On travaille dans le dossier /app de la boîte
WORKDIR /app

# On installe les bibliothèques
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# On copie mon code
COPY . .

# On lance
CMD ["python", "bot.py"]