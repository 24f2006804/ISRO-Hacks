# ARIS - Automated Resource Inventory System

ARIS is a sophisticated inventory management system designed specifically for space stations. It provides intelligent placement algorithms, waste management, and real-time monitoring of resources in space environments.

## Features

- **Smart Resource Placement**: Optimizes storage space using advanced placement algorithms
- **Real-time Monitoring**: Track inventory status and system health through an intuitive dashboard
- **Waste Management**: Intelligent waste identification and return planning
- **Space Simulation**: Test and validate inventory arrangements before implementation
- **Activity Logging**: Comprehensive logging of all inventory operations
- **Interactive 3D Visualization**: View and manage storage arrangements in 3D space

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/aris.git
cd aris

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Initialize the database
python -m app.utils.database
```

## Usage

```bash
# Start the server
uvicorn app.main:app --reload
```

Visit `http://localhost:8000` in your browser to access the application.

## Sample Data

The repository includes sample data files:
- `sample_items.csv`: Example inventory items
- `sample_containers.csv`: Example storage container configurations

## Configuration

Create a `.env` file in the root directory with the following variables:
```
DATABASE_URL=sqlite:///space_station.db
DEBUG=True
```

## Testing

```bash
pytest tests/
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

MIT License - see LICENSE file for details