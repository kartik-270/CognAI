from neo4j import AsyncGraphDatabase, AsyncDriver
from typing import List, Dict, Any, Optional
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

class Neo4jMemoryClient:
    """
    Neo4j Graph Memory client enforcing strict row-level isolation for user_id.
    Handles entity relations and provides cascading delete logic for /forget-me.
    Note: Advanced graph algorithms like Personalized PageRank (PPR) are deferred to Phase 5.
    """
    def __init__(self):
        self.uri = settings.NEO4J_URI
        self.user = settings.NEO4J_USER
        self.password = settings.NEO4J_PASSWORD
        self._driver: Optional[AsyncDriver] = None

    async def get_driver(self) -> AsyncDriver:
        if self._driver is None:
            self._driver = AsyncGraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password)
            )
        return self._driver

    async def close(self):
        if self._driver is not None:
            await self._driver.close()
            self._driver = None

    async def add_entity_relation(
        self,
        user_id: str,
        subject: str,
        predicate: str,
        object_: str
    ) -> bool:
        """
        Creates (Subject)-[PREDICATE]->(Object) strictly bound to user_id.
        """
        driver = await self.get_driver()
        query = """
        MERGE (s:Entity {name: $subject, user_id: $user_id})
        MERGE (o:Entity {name: $object_, user_id: $user_id})
        MERGE (s)-[r:RELATION {type: $predicate, user_id: $user_id}]->(o)
        RETURN s, r, o
        """
        try:
            async with driver.session() as session:
                await session.run(
                    query,
                    user_id=user_id,
                    subject=subject.strip().lower(),
                    predicate=predicate.strip().upper(),
                    object_=object_.strip().lower()
                )
            return True
        except Exception as e:
            logger.error(f"Failed to write Neo4j relation for user {user_id}: {e}")
            return False

    async def get_user_subgraph(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Queries all entity relationships strictly matching user_id.
        """
        driver = await self.get_driver()
        query = """
        MATCH (s:Entity {user_id: $user_id})-[r:RELATION {user_id: $user_id}]->(o:Entity {user_id: $user_id})
        RETURN s.name AS subject, r.type AS predicate, o.name AS object
        LIMIT $limit
        """
        try:
            async with driver.session() as session:
                result = await session.run(query, user_id=user_id, limit=limit)
                records = await result.data()
                return records
        except Exception as e:
            logger.error(f"Failed to query Neo4j subgraph for user {user_id}: {e}")
            return []

    async def retrieve_subgraph(self, user_id: str, keywords: List[str], limit: int = 15) -> List[Dict[str, Any]]:
        """
        Phase 5 Graph Retrieval: Implements Multi-Hop Contextual Retrieval (PPR Proxy).
        Finds keyword matches, then expands 2 hops out to capture deeper relationships.
        """
        if not keywords:
            return []
            
        driver = await self.get_driver()
        query = """
        // 1. Find Seed Nodes (direct keyword match on entities)
        MATCH (n:Entity {user_id: $user_id})
        WHERE any(kw IN $keywords WHERE toLower(n.name) CONTAINS kw)
        WITH collect(n) AS seeds
        
        // 2. Include nodes connected via relation keyword matches
        OPTIONAL MATCH (s:Entity {user_id: $user_id})-[r:RELATION {user_id: $user_id}]->(o:Entity {user_id: $user_id})
        WHERE any(kw IN $keywords WHERE toLower(r.type) CONTAINS kw)
        WITH seeds, collect(s) AS s_nodes, collect(o) AS o_nodes
        WITH seeds + s_nodes + o_nodes AS all_seeds
        UNWIND all_seeds AS seed
        WITH DISTINCT seed
        
        // 3. Expand 2 hops from seeds (Simulated PPR / Spreading Activation)
        MATCH path = (seed)-[:RELATION*1..2]-(neighbor:Entity {user_id: $user_id})
        WHERE all(r_path IN relationships(path) WHERE r_path.user_id = $user_id)
          AND all(n_path IN nodes(path) WHERE n_path.user_id = $user_id)
        UNWIND relationships(path) AS r_exp
        WITH DISTINCT r_exp
        RETURN startNode(r_exp).name AS subject, r_exp.type AS predicate, endNode(r_exp).name AS object
        LIMIT $limit
        """
        try:
            async with driver.session() as session:
                result = await session.run(query, user_id=user_id, keywords=[k.lower() for k in keywords], limit=limit)
                records = await result.data()
                return records
        except Exception as e:
            logger.error(f"Failed to retrieve Neo4j graph data for user {user_id}: {e}")
            return []

    async def delete_user_graph_data(self, user_id: str) -> int:
        """
        Cascading delete for /forget-me compliance:
        Purges ALL nodes and relationships belonging to user_id.
        """
        driver = await self.get_driver()
        query = """
        MATCH (n {user_id: $user_id})
        DETACH DELETE n
        """
        try:
            async with driver.session() as session:
                result = await session.run(query, user_id=user_id)
                summary = await result.consume()
                nodes_deleted = summary.counters.nodes_deleted
                relationships_deleted = summary.counters.relationships_deleted
                logger.info(f"Neo4j cascade delete for user {user_id}: {nodes_deleted} nodes, {relationships_deleted} relations deleted.")
                return nodes_deleted
        except Exception as e:
            logger.error(f"Failed to delete Neo4j data for user {user_id}: {e}")
            raise e

neo4j_client = Neo4jMemoryClient()
