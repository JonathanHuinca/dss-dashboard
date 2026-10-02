import sys
from app.cli.seed import main as seed_main
from app.cli.train import main_train

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "seed-data":
        seed_main()
    elif cmd == "train-models":
        main_train()
    else:
        print("Comandos disponibles:")
        print("  python -m app.cli seed-data      — poblar hipertablas con datos base")
        print("  python -m app.cli train-models   — entrenar y serializar modelos Prophet")
        sys.exit(1)
