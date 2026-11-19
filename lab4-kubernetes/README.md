# Лабораторная работа 4 — отказоустойчивость платформы

Вариант 4: сервис онлайн-обучения из ЛР 2, PostgreSQL, MinIO с PersistentVolumeClaim для файлов и Redis для кеширования. Для API заданы startup, liveness и readiness probes, запросы ресурсов, HPA, PDB, Service и Ingress.

NetworkPolicy ограничивает входящие подключения к PostgreSQL подами API при условии, что CNI кластера поддерживает NetworkPolicy.

## Проверка без кластера

```bash
pip install pyyaml
python check_manifests.py
```

## Развёртывание при наличии ресурсов

```bash
docker build -t lab2-platform:v1 ../lab2-platform
docker build -t lab-minio:2025 ../lab2-platform/minio
k3d cluster create lab4 --agents 0 --port "8080:80@loadbalancer" --wait
k3d image import lab2-platform:v1 lab-minio:2025 -c lab4
kubectl apply -f k8s/
kubectl rollout status deployment/platform-api -n lab4
kubectl get all,pvc,ingress,hpa,pdb -n lab4
kubectl top nodes
```

Альтернатива ручным манифестам — `helm install platform ./chart -n lab4 --create-namespace`; параметры реплик, образа и HPA находятся в `chart/values.yaml`. Для обновления используется `helm upgrade`, для возврата — `helm rollback`.

Трек с одним узлом уменьшает потребление памяти; эксперимент с отказом отдельного узла на нём невозможен. PVC с `ReadWriteOnce` и локальным хранилищем привязан к узлу: перенос пода на другой узел и параллельное монтирование ограничены. MinIO и PostgreSQL здесь по одной реплике, поэтому API можно масштабировать, но сами хранилища остаются едиными точками отказа. Для production потребовались бы сетевое хранилище и отказоустойчивая конфигурация сервисов.

Значения в Secret являются учебными и должны быть заменены; Kubernetes Secret кодирует значения, но сам по себе не гарантирует их шифрование. Замеры времени восстановления и HPA нужно проводить на работающем кластере.
