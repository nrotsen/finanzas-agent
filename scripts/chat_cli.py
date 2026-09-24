"""
CLI para probar el agente local, simulando WhatsApp.

Uso:
    cp .env.example .env  # y completar los valores
    python -m scripts.chat_cli
"""
import select
import sys

from dotenv import load_dotenv

load_dotenv()  # carga variables desde .env (si existe) ANTES de importar el agente

from src.agents import build_personal_agent  # noqa: E402


def read_user_input(prompt: str = "vos > ") -> str | None:
    """
    Lee input del usuario. Si se pegaron varias líneas a la vez (multi-line
    paste), las concatena en un solo mensaje en vez de procesarlas como turnos
    separados. Devuelve None si llega EOF.
    """
    sys.stdout.write(prompt)
    sys.stdout.flush()
    first = sys.stdin.readline()
    if not first:
        return None
    lines = [first]
    # Peek: si hay líneas buffered (de un paste), las absorbemos.
    while select.select([sys.stdin], [], [], 0.05)[0]:
        line = sys.stdin.readline()
        if not line:
            break
        lines.append(line)
    return "".join(lines).strip()


def main():
    print("Agente personal listo. Escribí 'salir' para terminar.\n")
    agent = build_personal_agent()
    history: list[dict] = []

    while True:
        try:
            user = read_user_input()
        except KeyboardInterrupt:
            print()
            break
        if user is None:
            break
        if user.lower() in ("salir", "exit", "quit"):
            break
        if not user:
            continue

        history.append({"role": "user", "content": user})
        respuesta, history = agent.run(history)
        print(f"bot > {respuesta}\n")


if __name__ == "__main__":
    main()
