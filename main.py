import argparse
import os
import json
import re
import hashlib
import logging
import psycopg2
from typing import Optional, List, Generator
from dataclasses import dataclass, asdict
from xml.etree.ElementTree import iterparse
from datetime import datetime, timezone
from dacite import from_dict
from dacite.exceptions import MissingValueError
from fhir.resources.observation import Observation
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

# Setup logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Load DB config from environment
load_dotenv()
db_params = {
    "dbname": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "host": os.getenv("POSTGRES_HOST", "192.168.1.16"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
}

RECORD_TYPES = {
    "HKQuantityTypeIdentifierHeartRate": "HEART_RATE",
    "HKQuantityTypeIdentifierStepCount": "STEP_COUNT",
    "HKQuantityTypeIdentifierActiveEnergyBurned": "ENERGY_BURNED",
    "HKQuantityTypeIdentifierDistanceWalkingRunning": "DISTANCE_WALKED",
    "HKQuantityTypeIdentifierRestingHeartRate": "RESTING_HEART_RATE",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "HEART_RATE_VARIABILITY",
    "HKQuantityTypeIdentifierVO2Max": "VO2_MAX",
    "HKQuantityTypeIdentifierRespiratoryRate": "RESPIRATORY_RATE",
    "HKQuantityTypeIdentifierEnvironmentalAudioExposure": "ENVIRONMENT_LOUDNESS",
    "HKQuantityTypeIdentifierHeadphoneAudioExposure": "HEADPHONE_LOUDNESS",
    "HKQuantityTypeIdentifierTimeInDaylight": "TIME_IN_SUNLIGHT",
    "HKCategoryTypeIdentifierSleepAnalysis": "SLEEP_STAGE",
    "HKCategoryValueSleepAnalysisAsleepREM": "REM",
    "HKCategoryValueSleepAnalysisAsleepDeep": "DEEP",
    "HKCategoryValueSleepAnalysisAsleepCore": "LIGHT",
    "HKCategoryValueSleepAnalysisInBed": "IN_BED",
    "HKCategoryValueSleepAnalysisAwake": "AWAKE",
    "HKCategoryValueSleepAnalysisAsleepUnspecified": "ASLEEP_UNKNOWN_STAGE",
    "HKQuantityTypeIdentifierAppleExerciseTime": "EXERCISE_TIME",
    "HKQuantityTypeIdentifierBodyMass": "WEIGHT",
    "HKQuantityTypeIdentifierHeight": "HEIGHT",
}


@dataclass
class HealthKitRecord:
    type: str
    sourceName: str
    sourceVersion: str
    creationDate: str
    startDate: str
    endDate: str
    value: str
    device: Optional[str] = None
    unit: Optional[str] = None

    def __post_init__(self):
        if self.device:
            # Make the device name human readable
            match = re.search(r"name:([^,]+)", self.device)
            if match:
                self.device = match.group(1).strip()

        # Make source name human readable
        self.sourceName = re.sub(r"\s+", " ", self.sourceName).strip()
        start_date = self.convert_to_utc_time(self.startDate)
        end_date = self.convert_to_utc_time(self.endDate)
        self.startDate = start_date.isoformat()
        self.endDate = end_date.isoformat()

        # Sleep Records are handled differently
        if self.type == "HKCategoryTypeIdentifierSleepAnalysis":
            self.type = f"SLEEP_STAGE_{RECORD_TYPES[self.value]}"
            delta = end_date - start_date
            self.value = delta.total_seconds() / 60
            self.unit = "min"
        else:
            self.type = RECORD_TYPES[self.type]

    @staticmethod
    def convert_to_utc_time(time: str) -> datetime:
        dt = datetime.strptime(time, "%Y-%m-%d %H:%M:%S %z")
        return dt.astimezone(timezone.utc)


@dataclass
class LabData:
    test_name: str
    loinc_code: str
    result_value: float
    result_unit: str
    issued_datetime: str
    reference_range: Optional[str]


def read_health_data(
    export_path: str, batch_size: int = 5000
) -> Generator[List[HealthKitRecord], None, None]:
    health_records: List[HealthKitRecord] = []
    for _, elem in iterparse(export_path):
        if elem.tag == "Record":
            record = elem.attrib
            record_type = record["type"]
            if record_type in RECORD_TYPES:
                try:
                    health_records.append(
                        from_dict(data_class=HealthKitRecord, data=record)
                    )
                except MissingValueError:
                    logger.warning(f"Malformed Record: {record}")
            if len(health_records) >= batch_size:
                yield health_records
                health_records = []
        elem.clear()
    if health_records:
        yield health_records


def parse_lab_data(directory_path: str) -> List[LabData]:
    records = []
    for filename in os.listdir(directory_path):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(directory_path, filename)
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            if data.get("resourceType") != "Observation":
                continue
            observation = Observation(**data)
            if (
                observation.code
                and observation.valueQuantity
                and observation.referenceRange
            ):
                test_name = observation.code.text
                loinc_code = next(
                    (
                        c.code
                        for c in observation.code.coding
                        if "loinc.org" in (c.system or "")
                    ),
                    "N/A",
                )
                value = observation.valueQuantity.value
                unit = observation.valueQuantity.unit or ""
                ref_range = (
                    observation.referenceRange[0].text
                    if observation.referenceRange and observation.referenceRange[0].text
                    else ""
                )
                issued = observation.issued.isoformat() if observation.issued else None

                records.append(
                    LabData(
                        test_name=test_name,
                        loinc_code=loinc_code,
                        result_value=value,
                        result_unit=unit,
                        reference_range=ref_range,
                        issued_datetime=issued,
                    )
                )
        except Exception as e:
            logger.warning(f"Error parsing {filename}: {e}")
    return records


def cli():
    parser = argparse.ArgumentParser(
        description="Parse Apple Health and Lab Data to PostgreSQL"
    )
    parser.add_argument("path", help="Path to Apple Health export directory")
    parser.add_argument(
        "--insert-lab", action="store_true", help="Parse and insert Lab data"
    )
    args = parser.parse_args()

    export_xml_path = os.path.join(args.path, "export.xml")
    lab_dir_path = os.path.join(args.path, "clinical-records")

    conn = psycopg2.connect(**db_params)
    cursor = conn.cursor()

    # Create health table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS health_records (
            id TEXT PRIMARY KEY,
            type TEXT,
            value TEXT,
            unit TEXT,
            start_time TIMESTAMPTZ,
            end_time TIMESTAMPTZ,
            source_name TEXT,
            device TEXT
        );
    """
    )

    for records in read_health_data(export_xml_path):
        insert_query = """
        INSERT INTO health_records (
            id, type, source_name, start_time, end_time, value, device, unit
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING;
        """
        record_tuples = [
            (
                hashlib.sha256(json.dumps(asdict(r)).encode()).hexdigest(),
                r.type,
                r.sourceName,
                r.startDate,
                r.endDate,
                r.value,
                r.device,
                r.unit,
            )
            for r in records
        ]
        execute_batch(cursor, insert_query, record_tuples, page_size=1000)
        conn.commit()

    # Lab Data Handling
    if args.insert_lab:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS lab_data (
                id SERIAL PRIMARY KEY,
                test_name TEXT,
                loinc_code TEXT,
                result_value REAL,
                result_unit TEXT,
                reference_range TEXT,
                issued_datetime TIMESTAMPTZ
            );
        """
        )

        lab_records = parse_lab_data(lab_dir_path)
        insert_lab_query = """
        INSERT INTO lab_data (
            test_name, loinc_code, result_value, result_unit, reference_range, issued_datetime
        ) VALUES (%s, %s, %s, %s, %s, %s);
        """
        lab_tuples = [
            (
                l.test_name,
                l.loinc_code,
                l.result_value,
                l.result_unit,
                l.reference_range,
                l.issued_datetime,
            )
            for l in lab_records
        ]
        execute_batch(cursor, insert_lab_query, lab_tuples, page_size=500)
        conn.commit()

    conn.close()


if __name__ == "__main__":
    cli()
