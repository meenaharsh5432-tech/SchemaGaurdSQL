import json
from collections import deque
from dataclasses import dataclass
from threading import Lock
import re

from app.retrieval.embeddings import (
    EMBEDDING_MODEL,
    cosine_similarity,
    embed_texts,
)
from app.retrieval.schema_cache import SchemaSnapshot


@dataclass(frozen=True)
class RetrievedSchema:
    prompt: str
    schema_version: str
    selected_tables: tuple[str, ...]
    ranking: tuple[tuple[str, float], ...]


def shortest_path(graph, start, target):
    queue = deque([(start, [start])])
    visited = {start}

    while queue:
        node, path = queue.popleft()

        if node == target:
            return path

        for neighbor in sorted(graph[node]):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))

    return None

def explicitly_mentioned_tables(
    question: str,
    table_names: list[str],
) -> set[str]:
    words = set(re.findall(r"[a-z0-9]+", question.lower()))
    mentioned = set()

    for qualified_name in table_names:
        table_name = qualified_name.rsplit(".", 1)[-1]

        # Match the full table phrase, e.g. "support tickets",
        # and a simple singular form, e.g. "support ticket".
        phrase = table_name.replace("_", " ")
        variants = {phrase}

        if phrase.endswith("s"):
            variants.add(phrase[:-1])

        for variant in variants:
            pattern = r"\b" + r"\s+".join(
                re.escape(word) for word in variant.split()
            ) + r"\b"

            if re.search(pattern, question.lower()):
                mentioned.add(qualified_name)
                break

        # Single-word names: "customer" / "customers".
        if "_" not in table_name:
            aliases = {table_name}
            if table_name.endswith("s"):
                aliases.add(table_name[:-1])

            if words & aliases:
                mentioned.add(qualified_name)

    return mentioned


class SchemaRetriever:
    def __init__(self):
        self._lock = Lock()
        self._index_key = None
        self._vectors = ()

    def retrieve(
        self,
        question: str,
        snapshot: SchemaSnapshot,
        *,
        top_k: int = 4,
    ) -> RetrievedSchema:
        if not question.strip():
            raise ValueError("Question cannot be blank")

        if top_k < 1:
            raise ValueError("top_k must be positive")

        metadata = json.loads(snapshot.prompt)
        tables = sorted(metadata["tables"], key=lambda t: t["table"])

        if not tables:
            raise ValueError("No allowed tables are available")

        names = [table["table"] for table in tables]
        index_key = (snapshot.version, EMBEDDING_MODEL)

        # Build one table index per schema/model combination.
        # Publish it only after all embeddings succeed.
        with self._lock:
            if self._index_key != index_key:
                documents = [
                    json.dumps(table, ensure_ascii=False, sort_keys=True)
                    for table in tables
                ]
                vectors = tuple(embed_texts(documents))
                self._vectors = vectors
                self._index_key = index_key

            table_vectors = self._vectors

        question_vector = embed_texts([question])[0]

        ranking = tuple(
            sorted(
                (
                    (name, cosine_similarity(vector, question_vector))
                    for name, vector in zip(names, table_vectors)
                ),
                key=lambda item: (-item[1], item[0]),
            )
        )

        best_score = ranking[0][1]

        if best_score <= 0:
            # Similarities provide no useful positive signal.
            # Preserve coverage by supplying the full schema.
            seeds = names
        else:
            cutoff = best_score * 0.65
            seeds = [
                name
                for name, score in ranking[:top_k]
                if score >= cutoff
            ]

        explicit_tables = explicitly_mentioned_tables(question, names)
        seeds = sorted(set(seeds) | explicit_tables)

        selected = set(seeds)

        selected = set(seeds)

        # Relationships are traversable in both directions.
        graph = {name: set() for name in names}

        for table in tables:
            source = table["table"]
            for foreign_key in table["foreign_keys"]:
                target = foreign_key["referenced_table"]
                if target in graph:
                    graph[source].add(target)
                    graph[target].add(source)

        # Include intermediate tables needed to join ranked tables.
        for index, source in enumerate(seeds):
            for target in seeds[index + 1:]:
                path = shortest_path(graph, source, target)
                if path is not None:
                    selected.update(path)

        selected_metadata = []

        for table in tables:
            if table["table"] not in selected:
                continue

            # Avoid exposing references to omitted table definitions.
            selected_metadata.append({
                **table,
                "foreign_keys": [
                    foreign_key
                    for foreign_key in table["foreign_keys"]
                    if foreign_key["referenced_table"] in selected
                ],
            })

        prompt = json.dumps(
            {
                "dialect": metadata["dialect"],
                "tables": selected_metadata,
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        return RetrievedSchema(
            prompt=prompt,
            schema_version=snapshot.version,
            selected_tables=tuple(sorted(selected)),
            ranking=ranking,
        )


schema_retriever = SchemaRetriever()