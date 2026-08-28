import os

import boto3


AWS_REGION = os.getenv(
    "AWS_REGION",
    "us-east-2",
)


def get_bedrock_agent_runtime():
    return boto3.client(
        "bedrock-agent-runtime",
        region_name=AWS_REGION,
    )


def build_data_source_filter(
    data_source_ids: list[str],
):
    ids = list(
        dict.fromkeys(
            value
            for value in data_source_ids
            if value
        )
    )

    if not ids:
        return None

    if len(ids) == 1:
        return {
            "equals": {
                "key":
                    "x-amz-bedrock-kb-data-source-id",
                "value":
                    ids[0],
            }
        }

    return {
        "orAll": [
            {
                "equals": {
                    "key":
                        "x-amz-bedrock-kb-data-source-id",
                    "value":
                        data_source_id,
                }
            }
            for data_source_id
            in ids
        ]
    }


def retrieve_knowledge(
    *,
    knowledge_base_id: str,
    query: str,
    data_source_ids: list[str],
    number_of_results: int = 5,
):
    vector_config = {
        "numberOfResults":
            number_of_results,
    }

    retrieval_filter = (
        build_data_source_filter(
            data_source_ids
        )
    )

    if retrieval_filter:
        vector_config[
            "filter"
        ] = retrieval_filter

    response = (
        get_bedrock_agent_runtime()
        .retrieve(
            knowledgeBaseId=
                knowledge_base_id,

            retrievalQuery={
                "text":
                    query,
            },

            retrievalConfiguration={
                "vectorSearchConfiguration":
                    vector_config,
            },
        )
    )

    return [
        {
            "text":
                result
                .get("content", {})
                .get("text", ""),

            "score":
                result.get(
                    "score"
                ),

            "location":
                result.get(
                    "location"
                ),

            "metadata":
                result.get(
                    "metadata",
                    {},
                ),
        }
        for result
        in response.get(
            "retrievalResults",
            []
        )
    ]


def knowledge_base_is_available_for_store(
    knowledge_base,
    store_id: int | None,
):
    if not knowledge_base.active:
        return False

    if knowledge_base.scope == "organization":
        return True

    if store_id is None:
        return False

    return any(
        store.id == store_id
        and store.active
        for store in knowledge_base.stores
    )


def retrieve_agent_knowledge(
    *,
    agent,
    query: str,
    store_id: int | None = None,
    number_of_results: int = 5,
):
    grouped_sources: dict[
        str,
        list[str],
    ] = {}

    for knowledge_base in (
        agent.knowledge_bases
    ):
        if not (
            knowledge_base_is_available_for_store(
                knowledge_base,
                store_id,
            )
        ):
            continue

        bedrock_kb_id = (
            knowledge_base.external_id
        )

        data_source_id = (
            knowledge_base
            .external_data_source_id
        )

        if (
            not bedrock_kb_id
            or not data_source_id
        ):
            continue

        grouped_sources.setdefault(
            bedrock_kb_id,
            [],
        ).append(
            data_source_id
        )

    all_results = []

    for (
        bedrock_kb_id,
        data_source_ids,
    ) in grouped_sources.items():
        results = retrieve_knowledge(
            knowledge_base_id=
                bedrock_kb_id,

            query=
                query,

            data_source_ids=
                data_source_ids,

            number_of_results=
                number_of_results,
        )

        for result in results:
            result[
                "knowledge_base_id"
            ] = bedrock_kb_id

        all_results.extend(
            results
        )

    all_results.sort(
        key=lambda item:
            item.get("score")
            or 0,
        reverse=True,
    )

    return all_results[
        :number_of_results
    ]
