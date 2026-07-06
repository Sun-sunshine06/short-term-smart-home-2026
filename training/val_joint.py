import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate an object-only multi-class YOLO detector.")
    parser.add_argument("--data", required=True, help="Path to Ultralytics data.yaml.")
    parser.add_argument("--model", required=True, help="Path to trained weights, for example best.pt.")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", default=None)
    parser.add_argument("--split", default="val", choices=["train", "val", "test"])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_path = Path(args.data)
    model_path = Path(args.model)
    if not data_path.exists():
        raise FileNotFoundError(f"data yaml not found: {data_path}")
    if not model_path.exists():
        raise FileNotFoundError(f"model weights not found: {model_path}")

    from ultralytics import YOLO

    model = YOLO(str(model_path))
    val_kwargs = {
        "data": str(data_path),
        "imgsz": args.imgsz,
        "batch": args.batch,
        "split": args.split,
    }
    if args.device is not None:
        val_kwargs["device"] = args.device

    model.val(**val_kwargs)


if __name__ == "__main__":
    main()
