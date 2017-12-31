import asyncio
import random
import logging
from .BaseGetter import BaseGetter
from ..Config.MainConfig import main_config


class ESScrollGetter(BaseGetter):
    def __init__(self, config):
        if not main_config.has_es_configured:
            raise ValueError("You must config es_hosts before using ESGetter, Please edit configure file: %s" % (main_config.ini_path, ))

        super().__init__(self)
        self.config = config
        self.es_client = config.es_client

        self.total_size = None
        self.result = None
        self.curr_size = 0

    def __aiter__(self):
        return self

    def init_val(self):
        self.total_size = None
        self.result = None
        self.curr_size = 0

    async def __anext__(self, retry=1):
        if self.total_size is None:
            self.result = await self.es_client.search(self.config.indices, self.config.doc_type, scroll="1m", body=self.config.query_body)
            self.total_size = self.result['hits']['total']
            self.total_size = self.config.max_limit if (self.config.max_limit and self.config.max_limit < self.result['hits']['total']) else self.total_size
            self.curr_size += len(self.result['hits']['hits'])
            logging.info("Get %d items from %s, percentage: %.2f%%" %
                         (len(self.result['hits']['hits']), self.config.indices + "->" + self.config.doc_type,
                          self.curr_size / self.total_size * 100))
            return [i["_source"] for i in self.result['hits']['hits']] if self.config.return_source else self.result

        if "_scroll_id" in self.result and self.result["_scroll_id"] and self.curr_size < self.config.max_limit:
            try:
                self.result = await self.es_client.scroll(scroll_id=self.result["_scroll_id"], scroll="1m")
            except Exception as e:
                if retry < self.config.max_retry:
                    await asyncio.sleep(random.randint(self.config.random_min_sleep, self.config.random_max_sleep))
                    return await self.__anext__(retry+1)
                else:
                    logging.error("Give up es getter, After retry: %d times, still fail to get result: %s" % (self.config.max_retry, str(e)))
                    raise StopAsyncIteration

            self.curr_size += len(self.result['hits']['hits'])
            logging.info("Get %d items from %s, percentage: %.2f%%" %
                         (len(self.result['hits']['hits']), self.config.indices + "->" + self.config.doc_type,
                          self.curr_size / self.total_size * 100))
            return [i["_source"] for i in self.result['hits']['hits']] if self.config.return_source else self.result

        self.init_val()
        logging.info("get source done: %s" % (self.config.indices + "->" + self.config.doc_type, ))
        raise StopAsyncIteration

    async def delete_all(self):
        """
        inefficient delete
        """
        body = {
            "query": {
                "match_all": {}
            }
        }
        result = await self.config.es_client.delete_by_query(index=self.config.indices, doc_type=self.config.doc_type,
                                                             body=body)
        return result

    def __iter__(self):
        raise ValueError("ESGetter must be used with async generator, not normal generator")