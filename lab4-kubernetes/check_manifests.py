from pathlib import Path
import yaml

files = sorted((Path(__file__).parent / 'k8s').glob('*.yaml'))
objects = [obj for path in files for obj in yaml.safe_load_all(path.read_text(encoding='utf-8')) if obj]
lookup = {(obj['kind'], obj['metadata']['name']): obj for obj in objects}
deployment = lookup['Deployment', 'platform-api']
container = deployment['spec']['template']['spec']['containers'][0]
assert all(probe in container for probe in ('startupProbe', 'livenessProbe', 'readinessProbe'))
assert container['resources']['requests']['cpu']
assert lookup['HorizontalPodAutoscaler', 'platform-api']['spec']['scaleTargetRef']['name'] == 'platform-api'
assert lookup['PersistentVolumeClaim', 'lesson-files']['spec']['accessModes'] == ['ReadWriteOnce']
assert lookup['Service', 'platform-api']['spec']['selector'] == deployment['spec']['selector']['matchLabels']
print(f'Validated {len(objects)} YAML resources: probes, HPA, service selector and persistent storage.')
