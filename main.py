import json
import os
import time

from automation import processar_vivo_free, get_user_balance, redeem_package

DATA_FILE = "user_session.json"  # Arquivo para simular o armazenamento persistente


def load_session():
    """Carrega o número e o token salvos do arquivo de sessão."""
    full_path = os.path.abspath(DATA_FILE)
    print(f"INFO: Tentando carregar sessão de: {full_path}")

    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
            print(
                f"INFO: Sessão encontrada. Token salvo em: {time.ctime(data.get('timestamp', 0))}"
            )
            return data.get("numero"), data.get("auth_token")
        except json.JSONDecodeError:
            print(
                f"❌ JSON corrompido em {DATA_FILE}. Iniciando nova sessão."
            )
            return None, None
        except Exception as e:
            print(f"❌ Erro ao carregar sessão: {e}. Iniciando nova sessão.")
            return None, None

    print(f"INFO: Arquivo de sessão '{DATA_FILE}' não encontrado. Nova sessão necessária.")
    return None, None


def save_session(numero, auth_token):
    """Salva o número e o token em um arquivo para persistência."""
    data = {"numero": numero, "auth_token": auth_token, "timestamp": time.time()}
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=4)
        print(f"✅ Sessão salva com sucesso em: {os.path.abspath(DATA_FILE)}")
    except Exception as e:
        print(f"❌ ERRO CRÍTICO ao salvar a sessão: {e}")
        print("AVISO: Sua sessão não será restaurada na próxima execução.")


def main_flow():
    numero, auth_token = load_session()

    if auth_token and numero:
        print(f"\n--- Sessão Restaurada para o número {numero} ---")
        print("Token encontrado. Pulando login.")
    else:
        print("\n--- INÍCIO: Nova Sessão (Login Necessário) ---")

        numero = input("📞 Digite seu número (DDD + Número): ").strip()

        print("\n== 1) Pedir SMS PIN ==")
        step1 = processar_vivo_free(numero, code=None)
        print(step1)

        if not step1.get("success"):
            print(step1.get("message", "Falha ao solicitar SMS."))
            return

        codigo = input("\n🔑 Digite o código SMS recebido: ").strip()

        print("\n== 2) Validar PIN e obter token ==")
        step2 = processar_vivo_free(numero, code=codigo)
        print(step2)

        if not step2.get("success"):
            print(step2.get("message", "Falha ao validar código."))
            return

        auth_token = step2.get("auth_token")
        if not auth_token:
            print("❌ Não veio auth_token na validação. Não dá pra seguir.")
            return

        save_session(numero, auth_token)

    print("\n--- Operações Autenticadas ---")

    print("\n== 3) Consultar saldo ==")
    saldo = get_user_balance(auth_token, numero)
    print(f"Saldo retornado: {saldo}")

    if saldo is None:
        print("❌ Não foi possível buscar o saldo (token inválido/expirado ou endpoint bloqueado).")
        return

    print(f"\n💰 Saldo de Moedas: {saldo}")

    print("\n✅ Fluxo básico OK (login + saldo).")
    print("Se quiser testar resgate, descomenta a parte abaixo no main.py.")

    # === Teste de resgate (cuidado) ===
    # package_id_to_redeem = 16
    # success, message, _ = redeem_package(auth_token, package_id_to_redeem, numero)
    # print(f"\n[RESGATE {package_id_to_redeem}] Sucesso: {success}. Mensagem: {message}")


if __name__ == "__main__":
    main_flow()