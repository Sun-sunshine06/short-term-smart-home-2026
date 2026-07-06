import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train an object-only multi-class YOLO detector.")
    parser.add_argument("--data", required=True, help="Path to Ultralytics data.yaml.")
    parser.add_argument("--model", default="yolo26s.pt", help="Pretrained model, for example yolo26s.pt.")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", default=None, help="Device id, for example 0, 0,1, cpu, or leave unset.")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--project", default="runs/object_yolo26")
    parser.add_argument("--name", default="object")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--patience", type=int, default=50)
    parser.add_argument("--cache", default=False, help="Ultralytics cache option: False, ram, or disk.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_path = Path(args.data)
    if not data_path.exists():
        raise FileNotFoundError(f"data yaml not found: {data_path}")

    from ultralytics import YOLO

    model = YOLO(args.model)
    train_kwargs = {
        "data": str(data_path),
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "workers": args.workers,
        "seed": args.seed,
        "project": args.project,
        "name": args.name,
        "resume": args.resume,
        "patience": args.patience,
        "cache": args.cache,
    }
    if args.device is not None:
        train_kwargs["device"] = args.device

    model.train(**train_kwargs)


if __name__ == "__main__":
    main()
