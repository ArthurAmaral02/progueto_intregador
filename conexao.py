import mysql.connector

def conectar():
    try:
        conexao = mysql.connector.connect(
            host="localhost",
            user="root",
            password="",
            database="ecommerce",
            port=3306
        )
        print("✅ Conectado ao MySQL com sucesso!")
        return conexao
    except mysql.connector.Error as err:
        print(f"[ERRO] Falha na conexão: {err}")
        return None

if __name__ == "__main__":
    conectar()