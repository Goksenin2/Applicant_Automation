"""Minimal monday.com GraphQL client: read board items, fetch file assets, write columns."""

import json

import requests

API_URL = "https://api.monday.com/v2"
API_VERSION = "2025-04"

ITEM_FIELDS = "id name column_values { id type text value }"


class MondayError(RuntimeError):
    pass


class MondayClient:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": token, "API-Version": API_VERSION, "Content-Type": "application/json"}
        )

    def query(self, query: str, variables: dict | None = None) -> dict:
        resp = self.session.post(API_URL, json={"query": query, "variables": variables or {}}, timeout=60)
        resp.raise_for_status()
        body = resp.json()
        if body.get("errors") or body.get("error_message"):
            raise MondayError(body.get("errors") or body.get("error_message"))
        return body["data"]

    def list_columns(self, board_id: int) -> list[dict]:
        data = self.query(
            "query ($b: [ID!]) { boards(ids: $b) { name columns { id title type } } }",
            {"b": [board_id]},
        )
        if not data["boards"]:
            raise MondayError(f"Board {board_id} not found (check the ID and your access).")
        return data["boards"][0]["columns"]

    def get_items(self, board_id: int) -> list[dict]:
        """Every item on the board, following the pagination cursor."""
        data = self.query(
            f"query ($b: [ID!]) {{ boards(ids: $b) {{ items_page(limit: 100) {{ cursor items {{ {ITEM_FIELDS} }} }} }} }}",
            {"b": [board_id]},
        )
        page = data["boards"][0]["items_page"]
        items = page["items"]
        while page["cursor"]:
            data = self.query(
                f"query ($c: String!) {{ next_items_page(limit: 100, cursor: $c) {{ cursor items {{ {ITEM_FIELDS} }} }} }}",
                {"c": page["cursor"]},
            )
            page = data["next_items_page"]
            items.extend(page["items"])
        return items

    def get_asset(self, asset_id: int) -> dict:
        """Asset metadata incl. public_url (a signed link that expires after ~1 hour)."""
        data = self.query(
            "query ($ids: [ID!]!) { assets(ids: $ids) { id name file_extension public_url } }",
            {"ids": [asset_id]},
        )
        if not data["assets"]:
            raise MondayError(f"Asset {asset_id} not found.")
        return data["assets"][0]

    def update_columns(self, board_id: int, item_id: str, values: dict) -> None:
        self.query(
            "mutation ($b: ID!, $i: ID!, $v: JSON!) {"
            " change_multiple_column_values(board_id: $b, item_id: $i, column_values: $v,"
            " create_labels_if_missing: true) { id } }",
            {"b": board_id, "i": item_id, "v": json.dumps(values)},
        )


def column_map(item: dict) -> dict[str, dict]:
    return {cv["id"]: cv for cv in item["column_values"]}


def file_asset_ids(column_value: dict | None) -> list[int]:
    """Asset IDs of files uploaded to a File column (ignores Drive/Dropbox links)."""
    if not column_value or not column_value.get("value"):
        return []
    files = json.loads(column_value["value"]).get("files", [])
    return [int(f["assetId"]) for f in files if f.get("assetId")]
