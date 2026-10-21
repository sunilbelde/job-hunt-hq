# Profile

What you have done and can do beyond what `BASE.tex` states. Resume tailoring treats every entry here as
true, so leave out anything you could not discuss in an interview. Write one entry per line, starting with
"- ". Headings and other text are ignored.

## Experience

Facts about each job that `BASE.tex` does not say. Put them under a `###` heading naming the employer as
its job heading in `BASE.tex` starts ("Capital One", "Dockskiff"). A tailored bullet of that job may use
them like its base bullets, numbers included, and a posting keyword a fact states may appear in the
bullets that use it. A heading that names no job fails resume generation.

### Capital One
- Ran benchmark evaluations of the mapping agent, comparing different models, reasoning settings and prompt versions.
- Tuned prompts based on the benchmark results.
- Built feedback loops that fed evaluation results back into the agent's prompts and configuration.
- Led LLM performance regression and benchmarking of Mixtral, Llama, GPT-OSS 120B and other open models, comparing latency, accuracy, reasoning quality, hallucination rate and cost/efficiency to select the production model for code generation.
- The GenAI ETL framework generates production-ready ETL artifacts in PySpark and Scala, enabling no-code ETL workflow creation.
- Built a two-phase system: a Llama 3.3-70B model translates pseudocode to code, and a deterministic orchestration engine assembles and executes the ETL.
- Designed the end-to-end ETL DAG topology in Python/NetworkX, modeling dependencies across Source, Joiner, Filter, Transform, Target, Custom and Distinct components for fault-tolerant, lineage-aware workflow orchestration.
- Built the agentic RAG pipeline with LangChain and SimSearch vector retrieval, using few-shot and Chain-of-Thought prompting for context-grounded code generation.
- Improved retrieval quality by researching chunking strategies, embedding models and prompt-injection defenses.
- Ran performance and load testing with Apache JMeter to set SLA metrics for throughput, latency and reliability.

### University of Illinois Chicago
- Built a social influence prediction model using graph embeddings (node2vec, DeepWalk) and centrality-based features to quantify user impact and information diffusion across large social networks.

### Dockskiff
- Built a visual segmentation system with Faster-RCNN that identifies contract structure (headers, tables, clause blocks, footers, signature sections) for downstream parsing and analytics.
- Improved OCR accuracy with image preprocessing that included morphology filters alongside denoising and deskewing, reducing noise in the metadata pipelines.
- Used the Clause Classification Engine for compliance validation and risk scoring of contract clauses.
- Designed an automated NER data extraction and auto-labeling pipeline with Prodigy, cutting manual annotation effort by 60%.
- Enabled structured ingestion of contract tables into analytics databases, cutting manual data entry and review time by 70%.

### Acheron Software Consultancy
- Developed an internal TimeSheets management app and workflow applications with Spring Boot, Angular 8 and MySQL, delivering secure REST APIs and responsive UI used across project teams.
- Built and customized solutions on OpenText AppWorks BPM, automating document-centric workflows and speeding up approval cycles for enterprise clients.

## Skills and abilities

Skills you have beyond the resume. When a job posting asks for a keyword your base resume lacks, a
separate Claude judge decides whether you genuinely have it. A keyword it approves from this list alone can
appear in the resume's skills section, never inside an experience bullet. Name the tools you have used
rather than only the area: an entry "Browser automation" does not tell the judge you have used Playwright.

- Agent harnesses
- Testing
- Code quality
- Reliability
- Context engineering
- Post-training (supervised fine-tuning)
- Browser automation
- Playwright
- TypeScript

### GenAI and LLMs

- GenAI application architecture
- Agentic framework and multi-step agent system architecture
- Agent harness optimization
- Context optimization (context window management, prompt and tool context design)
- GPT-OSS 120B
- Mixtral
- LLM evaluation and benchmarking (latency, accuracy, reasoning quality, hallucination rate, cost)
- LLM regression testing across model versions
- Chain-of-Thought prompting
- Few-shot prompting
- Fine-tuning
- Supervised fine-tuning (SFT)
- LangGraph
- Claude Agent SDK
- Anthropic Claude API
- AWS Bedrock
- vLLM
- Ollama
- Arize Phoenix (LLM tracing and observability)
- Weights & Biases
- RAG retrieval tuning (chunking strategies, embedding choice)
- Prompt injection defenses
- Tool calling / function calling
- Structured outputs (JSON schema)
- Streaming LLM responses
- Token cost and latency optimization (token economics)
- Guardrails for LLM agents
- Agent permissions and data-access control for agents taking real actions
- Adversarial input and bad-actor detection
- Self-healing retries, error categorization and cross-provider failover
- Multi-agent orchestration
- Reranking
- Production log analysis to find agent and model failures
- ChromaDB

### AI-assisted development

- Claude Code
- OpenAI Codex
- GitHub Copilot
- AI coding agents and AI-assisted coding tools
- Model Context Protocol (MCP) servers and tools
- Claude Skills (using and writing skills)
- OpenSpec
- Spec-driven development

### Data engineering

- Scala
- ETL pipeline design (Source, Joiner, Filter, Transform, Target components)
- DAG orchestration with data lineage and fault tolerance
- Table extraction from documents into analytics databases
- Databricks
- Snowflake

### Performance and reliability

- Apache JMeter
- Performance and load testing
- SLA metrics (throughput, latency, reliability)

### Machine learning and NLP

- Deep learning
- XGBoost
- Search ranking and relevance
- Human-in-the-loop annotation and review systems
- BERT
- TF-IDF
- Multi-label classification
- Model evaluation metrics (Micro-F1, ROC-AUC, BLEU, PSNR, SSIM)
- Seq2Seq with attention
- LSTM and GRU
- Neural machine translation (English to Hindi and Telugu)
- Subword tokenization
- Graph embeddings (node2vec, DeepWalk)
- Social network analysis (centrality features, influence and information diffusion)
- Data labeling and auto-labeling pipelines (Prodigy)

### Computer vision

- Computer vision
- Image denoising (DnCNN, autoencoders)
- Image preprocessing (denoising, deskewing, morphology filters)
- Object detection (Faster-RCNN)
- Document layout analysis

### Software and visualization

- Microservices architecture
- FastAPI
- Flask
- Agile / Scrum
- Full-stack web development (production frontend and backend)
- OpenText AppWorks BPM (document workflow automation)
- Three.js
- D3.js
- Interactive data visualization dashboards
- Technical writing (Medium articles on ML projects)

### Research and documentation

- Applied research
- Evaluation design and experimentation
- Technical documentation
- Architecture diagrams (creating and maintaining)
- Technical design documents
- Zero-to-one product delivery as part of a team (idea to production)
- Mentoring engineers
