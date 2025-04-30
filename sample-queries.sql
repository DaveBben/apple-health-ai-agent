
-- Get table information
select column_name, data_type, character_maximum_length, column_default, is_nullable
from INFORMATION_SCHEMA.COLUMNS where table_name = 'data_dictionary';

select distinct(test_name) from lab_data;

-- Get one distnce record by type
SELECT DISTINCT ON (type) *
FROM health_records;



-- Look at one Record
SELECT *
FROM health_records



-- Steps taken yesterday
SELECT 
    COALESCE(SUM(CAST(value AS integer)), 0) AS total_steps_yesterday
FROM 
    health_records
WHERE 
    type = 'STEP_COUNT'
    AND start_time::date = CURRENT_DATE - INTERVAL '1 day';





-- Daily average heart rate over the past week:
SELECT 
    ROUND(AVG(CAST(value AS numeric)), 1) AS average_daily_heart_rate
FROM 
    health_records
WHERE 
    type = 'HEART_RATE'
    AND start_time >= CURRENT_DATE - INTERVAL '7 days'
    AND start_time <= CURRENT_DATE;


-- Get Database schema
SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';

-- Get total sleep time in minutes on the night of April 13th
SELECT 
  SUM(CAST(value AS numeric)) AS total_sleep_hours
FROM 
    health_records
WHERE 
    type LIKE 'SLEEP_STAGE_%'
    AND type != 'SLEEP_STAGE_AWAKE' 
    AND type != 'SLEEP_STAGE_IN_BED'
    AND start_time >= '2025-04-13 00:00:00'::timestamp
 	AND start_time < '2025-04-14 12:00:00'::timestamp;

-- squery lab data
select * from lab_data limit 5;

-- get AST lab data
SELECT 
    id,
    test_name,
    loinc_code,
    result_value,
    result_unit,
    reference_range,
    issued_datetime
FROM 
    lab_data
WHERE 
    test_name ILIKE '%AST%' 
    OR test_name ILIKE '%Aspartate%'
    OR loinc_code = '1920-8'  -- LOINC code for AST
ORDER BY 
    issued_datetime DESC;

 SELECT value, recorded_at FROM health_records WHERE type = 'WEIGHT' ORDER BY recorded_at DESC LIMIT 1;
 
 


  
  select CASE
      WHEN unit ILIKE '%lb%' THEN CAST(value AS numeric) * 0.453592
      WHEN unit ILIKE '%kg%' THEN CAST(value AS numeric)
    END AS weight_kg from health_records where type = 'WEIGHT' limit 1;


 



                


