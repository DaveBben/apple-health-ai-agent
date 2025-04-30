# Apple Health AI Agent
 I built a multi-agent AI system that reads my Apple Health and Labcorp data to answer real health-related questions.

 To get started, clone the repo then do
 
 ```
 uv sync
 ```

## Data Used
* Apple Health Data
* Labcorp Data (imported through Apple Health)

## Tools
* N8N
* PostgresQL
* Ollama

### Exporting Apple Health data
Unzip your Apple Health export to the root of this project folder. Then run the following command:

```
python main.py ./apple_health_export --insert-lab 
```

You can omit labs, if you are not extracting labs.

### Creating Vectors Embeddings
Use the following Python script:
``` 
python create_vector_db.py
```