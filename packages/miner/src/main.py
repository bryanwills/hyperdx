from typing import Any, Dict, List, Optional
import hashlib
import json
import time

from drain3 import TemplateMiner
from drain3.file_persistence import FilePersistence
from drain3.masking import MaskingInstruction
from drain3.template_miner_config import TemplateMinerConfig
from fastapi import FastAPI, Request
from pydantic import BaseModel

from .logger import logger
from .anomaly_detection import DEFAULT_CONFIG, DEFAULT_STRENGTH, DataPoint, detect_anomalies, detect_anomaly

API_VERSION = "0.0.1"

app = FastAPI()

def get_template_miner():
    persistence = FilePersistence("hdx_state.bin")
    config = TemplateMinerConfig()
    # config.load(dirname(__file__) + "/drain3.ini")
    config.profiling_enabled = True
    config.masking_instructions = [
        MaskingInstruction(
            "((?<=[^A-Za-z0-9])|^)([\\-\\+]?\\d+)((?=[^A-Za-z0-9])|$)", "NUM"
        ),
        MaskingInstruction(
            "((?<=[^A-Za-z0-9])|^)(\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3})((?=[^A-Za-z0-9])|$)",
            "IP",
        ),
    ]

    template_miner = TemplateMiner(persistence, config=config)

    return template_miner


def sha1_hash(string):
    sha1 = hashlib.sha1()
    sha1.update(string.encode("utf-8"))
    hashed_string = sha1.hexdigest()
    return hashed_string


class LogData(BaseModel):
    lines: List[List[str]]


class LogPattern(BaseModel):
    change_type: str
    cluster_count: int
    cluster_id: str
    cluster_size: int
    template_mined: str


# write me a flask endpoint that accepts a log message in the body of the request as JSON
# and returns the result of calling template_miner.add_log_message on that message
# as JSON in the response body
@app.post("/logs")
def post_log(log_data: LogData):
    logger.warning(
        json.dumps(
            {
                "message": "Processing logs",
                "lines": len(log_data.lines),
            }
        )
    )
    t1 = time.time()
    template_miner = get_template_miner()
    result = {}
    patterns = {}
    for line in log_data.lines:
        [log_id, log_body] = line
        pattern = template_miner.add_log_message(log_body)
        pattern_id = str(pattern["cluster_id"])
        patterns[pattern_id] = pattern["template_mined"]
        result[log_id] = pattern_id
        # if pattern['change_type'] == 'cluster_template_changed' or pattern['change_type'] == 'none':
        #     result[log_id] = pattern['template_mined']
    logger.warning(
        json.dumps(
            {
                "message": "Processed logs",
                "patterns": len(patterns),
                "lines": len(log_data.lines),
                "duration_ms": (time.time() - t1) * 1000,
                "duration_per_log_ms": ((time.time() - t1) / len(log_data.lines))
                * 1000,
            }
        )
    )
    return {
        "patterns": patterns,
        "result": result,
    }


@app.get("/health")
def health_check():
    logger.info("🐱 Health check !!!!")

    return {"status": "ok", "version": API_VERSION}

class DetectAnomaliesRequest(BaseModel):
    history: List[List[DataPoint]]
    strength: Optional[float] = DEFAULT_STRENGTH
    config: Optional[Dict[str, Any]] = DEFAULT_CONFIG
    
class DetectAnomalyRequest(BaseModel):
    history: List[DataPoint]
    current: DataPoint
    strength: Optional[float] = DEFAULT_STRENGTH
    config: Optional[Dict[str, Any]] = DEFAULT_CONFIG

@app.post("/detect_anomalies")
def detect_anomalies_endpoint(request: DetectAnomaliesRequest):
    history = request.history
    strength = request.strength
    config = request.config
    results = detect_anomalies(history, strength, config)
    
    logger.info(
        json.dumps(
            {
                "message": "Anomaly Detection Results: detect_anomalies",
                "results": [[item.dict() for item in service] for service in results],
            }
        )
    )
    
    return results

# TODO: make sure we have traces/spans in place to debug and benchmark this endpoint performance
@app.post("/detect_anomaly")
def detect_anomaly_endpoint(request: DetectAnomalyRequest):
    history = request.history
    current = request.current
    strength = request.strength
    config = request.config
    result = detect_anomaly(history, current, strength, config)
    
    logger.info(
        json.dumps(
            {
                "message": "Anomaly Detection Result: detect_anomaly",
                "result": result.dict(),
            }
        )
    )
    
    return result