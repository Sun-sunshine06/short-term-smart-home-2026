import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from sklearn.datasets import fetch_lfw_people, get_data_home

from face_service import verify_face


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and run a 2-authorized + 1-unknown face access demo from LFW.")
    parser.add_argument("--out", default="runs/face_access_demo", help="Output directory.")
    parser.add_argument("--gallery-count", type=int, default=5, help="Enrollment images per authorized person.")
    parser.add_argument("--threshold", type=float, default=0.40, help="Cosine similarity threshold.")
    parser.add_argument("--min-margin", type=float, default=0.05, help="Required top1-top2 score gap.")
    parser.add_argument("--det-size", type=int, default=640)
    parser.add_argument("--lfw-home", help="Path to sklearn lfw_home directory.")
    return parser.parse_args()


def ensure_lfw_root(lfw_home: str | None) -> Path:
    home = Path(lfw_home) if lfw_home else Path(get_data_home()) / "lfw_home"
    root = home / "lfw_funneled"
    if not root.exists():
        fetch_lfw_people(color=True, resize=1.0, min_faces_per_person=2)
    if not root.exists():
        raise FileNotFoundError(f"LFW funneled images not found: {root}")
    return root


def collect_people(root: Path, min_images: int) -> list[tuple[str, list[Path]]]:
    people: list[tuple[str, list[Path]]] = []
    for person_dir in sorted(root.iterdir()):
        if not person_dir.is_dir():
            continue
        images = sorted(person_dir.glob("*.jpg"))
        if len(images) >= min_images:
            people.append((person_dir.name, images))
    people.sort(key=lambda item: (-len(item[1]), item[0]))
    return people


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copy_image(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def build_gallery(out_dir: Path, authorized: list[tuple[str, list[Path]]], unknown: tuple[str, list[Path]], gallery_count: int) -> dict[str, Any]:
    gallery_dir = out_dir / "gallery"
    probes_dir = out_dir / "probes"
    reset_dir(gallery_dir)
    reset_dir(probes_dir)

    users = []
    true_probes = []
    for identity, images in authorized:
        user_dir = gallery_dir / identity
        for index, image in enumerate(images[:gallery_count], start=1):
            dst = user_dir / f"{index:03d}.jpg"
            copy_image(image, dst)
        probe = probes_dir / f"true_{identity}.jpg"
        copy_image(images[gallery_count], probe)
        users.append({"user_id": identity, "gallery_images": [str(user_dir / f"{i:03d}.jpg") for i in range(1, gallery_count + 1)]})
        true_probes.append({"expected": identity, "path": str(probe), "source": str(images[gallery_count])})

    unknown_name, unknown_images = unknown
    unknown_probe = probes_dir / f"fake_unknown_{unknown_name}.jpg"
    copy_image(unknown_images[0], unknown_probe)

    return {
        "gallery_dir": str(gallery_dir),
        "probes_dir": str(probes_dir),
        "authorized_users": users,
        "true_probes": true_probes,
        "fake_probe": {"expected": None, "source_identity": unknown_name, "path": str(unknown_probe), "source": str(unknown_images[0])},
    }


def run_access_tests(layout: dict[str, Any], threshold: float, min_margin: float, det_size: int) -> list[dict[str, Any]]:
    tests = []
    for probe in layout["true_probes"]:
        tests.append({"case": f"true_{probe['expected']}", "expected_user_id": probe["expected"], "expected_action": "unlock", "image_path": probe["path"]})
    fake = layout["fake_probe"]
    tests.append({"case": "fake_unknown", "expected_user_id": None, "expected_action": "deny", "image_path": fake["path"]})

    results = []
    for test in tests:
        result = verify_face(
            image_path=test["image_path"],
            gallery_dir=layout["gallery_dir"],
            threshold=threshold,
            min_margin=min_margin,
            det_size=det_size,
        )
        action = "unlock" if result["matched"] else "deny"
        passed = action == test["expected_action"]
        if test["expected_user_id"] is not None:
            passed = passed and result["user_id"] == test["expected_user_id"]
        results.append(
            {
                **test,
                "action": action,
                "passed": passed,
                "matched": result["matched"],
                "user_id": result["user_id"],
                "score": result["score"],
                "threshold": result["threshold"],
                "score_margin": result["score_margin"],
                "min_margin": result["min_margin"],
                "best_match": result["best_match"],
                "second_best_identity_match": result["second_best_identity_match"],
            }
        )
    return results


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    root = ensure_lfw_root(args.lfw_home)
    people = collect_people(root, args.gallery_count + 1)
    if len(people) < 3:
        raise RuntimeError("Need at least 3 LFW identities with enough images.")

    authorized = people[:2]
    unknown = people[2]
    layout = build_gallery(out_dir, authorized, unknown, args.gallery_count)
    results = run_access_tests(layout, args.threshold, args.min_margin, args.det_size)

    report = {
        "dataset": str(root),
        "purpose": "2 true authorized probes + 1 fake unknown probe face access demo",
        "threshold": args.threshold,
        "min_margin": args.min_margin,
        "gallery_count_per_user": args.gallery_count,
        "layout": layout,
        "results": results,
        "passed": all(item["passed"] for item in results),
    }
    report_path = out_dir / "face_access_demo_result.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"wrote: {report_path}")


if __name__ == "__main__":
    main()
