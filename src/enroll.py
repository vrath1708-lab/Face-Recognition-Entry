import argparse

from database import init_db, upsert_member
from face_service import build_embedding_from_image, vector_to_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enroll or update a premium member.")
    parser.add_argument("--member-id", required=True, help="Unique member ID")
    parser.add_argument("--name", required=True, help="Member full name")
    parser.add_argument("--image", required=True, help="Path to member face image")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    init_db()

    embedding = build_embedding_from_image(args.image)
    upsert_member(args.member_id, args.name, vector_to_csv(embedding))

    print(f"Enrolled member {args.member_id} ({args.name})")


if __name__ == "__main__":
    main()
