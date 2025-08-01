# Feature Request: Gateway-Worker Scraping System

## FEATURE:

Build a distributed web scraping system using Python with gateway-worker architecture. The system should handle scraping requests through a message queue, execute dynamic scripts, and return results synchronously to clients.

**Core Components:**

- **Gateway**: Receives scraping requests via HTTP API and forwards them to message queue
- **Message Queue**: Manages scraping tasks between gateway and workers using RabbitMQ RPC pattern
- **Worker**: Processes tasks from queue, downloads and executes scraping scripts in child processes
- **Script Storage**: External repository for site-specific and task-specific scraping scripts
- **Caching System**: Version-controlled caching of scraping scripts with modification time tracking

**Key Requirements:**

- Gateway-worker architecture with RabbitMQ RPC communication
- Dynamic script execution with child process isolation for security and stability
- Synchronous response delivery with timeout handling using correlation_id pattern
- Version-controlled script caching with automatic updates based on modification time
- Flexible input parameter system for script execution
- Support for HTTP scraping, captcha handling (pydoll), and browser automation
- Site-specific and task-specific script management

**Technical Specifications:**

- Language: Python
- Architecture: Distributed gateway-worker pattern
- Message Queue: RabbitMQ with RPC pattern (correlation_id, reply_to)
- Script Storage: External repository with version control (supports Git, HTTP, S3, etc.)
- Execution: Child process isolation for security and worker stability
- Caching: Modification time comparison and conditional downloads to local disk
- Protocols: HTTP for scraping, browser automation when needed

## EXAMPLES:

Currently the examples/ folder is empty. Please create the following examples during implementation:

- `gateway/` - API gateway patterns and request handling
- `worker/` - Worker process patterns and task execution
- `queue/` - RabbitMQ RPC integration patterns
- `script_manager/` - Script downloading, caching, and version management
- `scrapers/` - Sample scraping script templates
- `models/` - Data models for requests, responses, and configurations
- `tests/` - Testing patterns for distributed systems

## DOCUMENTATION:

**Message Queue Systems:**

- https://www.rabbitmq.com/tutorials/tutorial-six-python.html (RabbitMQ RPC)
- https://pika.readthedocs.io/en/stable/ (Pika - Python RabbitMQ client)
- https://aio-pika.readthedocs.io/en/latest/ (Async RabbitMQ client)

**Web Scraping Libraries:**

- https://requests.readthedocs.io/en/latest/
- https://docs.aiohttp.org/en/stable/
- https://beautiful-soup-4.readthedocs.io/en/latest/
- https://scrapy.readthedocs.io/en/latest/

**Browser Automation:**

- https://playwright.dev/python/
- https://selenium-python.readthedocs.io/
- https://pypi.org/project/pydoll/ (for captcha handling)

**Process Management:**

- https://docs.python.org/3/library/subprocess.html
- https://docs.python.org/3/library/multiprocessing.html

**API Framework:**

- https://fastapi.tiangolo.com/
- https://flask.palletsprojects.com/

## OTHER CONSIDERATIONS:

**Architecture Recommendations:**

- Use RabbitMQ as message broker for robust RPC-style communication
- Implement FastAPI for gateway REST API with async/await support
- Use aio-pika for asynchronous RabbitMQ communication
- Consider Docker containers for worker isolation
- Implement health checks for worker monitoring

**Security & Isolation:**

- Run scraping scripts in sandboxed child processes to prevent script failures from crashing the worker process
- Implement script validation before execution
- Use resource limits (CPU, memory, timeout) for script execution
- Validate and sanitize input parameters

**Scalability & Performance:**

- Design for horizontal worker scaling
- Implement connection pooling for HTTP requests
- Use async/await patterns where possible
- Consider worker specialization by site or task type

**Error Handling & Monitoring:**

- Implement comprehensive logging in Korean
- Add retry mechanisms with exponential backoff
- Monitor worker health and queue status
- Handle script download failures gracefully

**Script Management:**

- Use modification time tracking for script version control
- Workers check local cached script modification time against remote repository
- Download and cache scripts only when remote version is newer
- Store cached scripts in worker's local disk at designated path
- Implement script metadata (dependencies, requirements)
- Support for script-specific configuration
- Script storage supports Git, HTTP, and S3-compatible object storage
- S3 is recommended for large-scale or cloud-native deployments

**Data Flow:**

1. Client → Gateway (HTTP request with script info + parameters)
2. Gateway → RabbitMQ (task creation with correlation_id and reply_to queue)
3. Worker → Script Storage (modification time check + download if needed)
4. Worker → Child Process (script execution with parameters for isolation)
5. Worker → Gateway (result delivery via reply_to queue with correlation_id)
6. Gateway → Client (HTTP response with timeout handling)

**Additional Components to Consider:**

- **Database**: For task history, worker status, and script metadata
- **Load Balancer**: For multiple gateway instances
- **Monitoring Dashboard**: For system health and performance metrics
- **Rate Limiting**: Per-site and per-client request limits
- **Result Storage**: For large scraping results (optional async delivery)
- **Authentication**: API key or token-based access control

**Environment Configuration Examples:**

Git Repository:

```
SCRIPT_REPOSITORY_TYPE=git
SCRIPT_REPOSITORY_URL=https://github.com/your-org/scraping-scripts
```

HTTP Repository:

```
SCRIPT_REPOSITORY_TYPE=http
SCRIPT_REPOSITORY_URL=https://api.example.com/scripts
```

S3 Repository:

```
SCRIPT_REPOSITORY_TYPE=s3
S3_BUCKET_NAME=your-scraping-scripts-bucket
S3_REGION=ap-northeast-2
S3_ACCESS_KEY=your-access-key
S3_SECRET_KEY=your-secret-key
S3_PREFIX=scripts/  # Optional prefix for organization
```

RabbitMQ Configuration:

```
RABBITMQ_URL=amqp://user:password@localhost:5672/
RABBITMQ_TASK_QUEUE=scraping_tasks
RABBITMQ_RESULT_TIMEOUT=300  # seconds
```

## PRP Generation Plan

**System Complexity Analysis:**
This Gateway-Worker Scraping System consists of 5 major components forming a distributed system that is too complex to manage with a single PRP. Each component should be developed and tested independently, requiring a phased approach to PRP generation.

**PRP Generation Order (Dependency Consideration):**

### Phase 1: Foundation Infrastructure

**PRP-1: Core Models & Shared Components**

- Data model definitions (Request, Response, Task, Script, etc.)
- Common utilities and configuration management
- Basic exception handling and logging system
- Dependencies: None (implement first)

### Phase 2: Message Queue System

**PRP-2: RabbitMQ RPC Communication System**

- RabbitMQ-based RPC pattern implementation
- Task queue management with correlation_id and reply_to
- Worker health checks and monitoring
- Dependencies: PRP-1 (uses common models)

### Phase 3: Script Management System

**PRP-3: Script Manager**

- Script downloads from external repositories
- Modification time-based version control and caching system
- Script metadata management
- Dependencies: PRP-1 (uses common models)

### Phase 4: Worker System

**PRP-4: Worker System**

- Task retrieval from RabbitMQ queue
- Script execution in child processes for isolation
- Result processing and error handling
- Dependencies: PRP-1, PRP-2, PRP-3 (uses all previous components)

### Phase 5: Gateway API

**PRP-5: Gateway API**

- FastAPI-based REST API implementation
- Request validation and RabbitMQ RPC forwarding
- Synchronous response handling with correlation_id (with timeout)
- Dependencies: PRP-1, PRP-2 (uses models and queue system)

### Phase 6: System Integration & Optimization

**PRP-6: Integration & Optimization**

- Full system integration testing
- Performance optimization and monitoring
- Error handling and recovery mechanisms
- Dependencies: PRP-1~5 (integrates all components)

**Each PRP Components:**

- **Critical Context**: Relevant documentation and examples for each component
- **Implementation Blueprint**: Detailed implementation plans and pseudocode
- **Validation Gates**: Component-specific testing strategies
- **Dependencies**: Previous PRP completion verification requirements

**Recommended Development Approach:**

1. Progress through each Phase sequentially
2. Verify validation gates pass after each PRP completion
3. Ensure previous component stability before proceeding to next Phase
4. Perform basic end-to-end testing after Phase 4 completion

This phased approach enables systematic construction of complex distributed systems.
