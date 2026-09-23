# upstream/main + StepCache 병합 기록

## 1. 기준과 목표

- 기준 upstream: `fd80dc4` (`Merge pull request #489 ...`). 작업 시작 당시 로컬 `HEAD`와 `upstream/main`이 같은 커밋이었다.
- 적용 중이던 커밋: `e46bf79` (`Add TOPP step cache, ported from quantms-web`).
- 충돌 파일: `src/workflow/CommandExecutor.py`.
- 목표: upstream의 실행 결과, 스레드 설정, 진행 상태, 오류 보고, 파라미터 처리와 StepCache의 재사용·무효화·의존성 연결을 함께 유지한다.

이 문서는 위 로컬 기준 커밋에 대한 병합 설명이다. 원격 main의 이후 변경까지 포함했다는 의미는 아니다.

## 2. 충돌을 어느 쪽 기준으로 해결했는가

| 영역 | 유지/추가한 동작 |
| --- | --- |
| import / 초기화 | upstream의 `resolve_thread_setting`, vendor 변환, `RunProgress`, `deque`를 유지하고 `StepCache`를 추가 |
| 스레드 계산 | upstream의 `_get_max_threads()`를 그대로 유지 |
| TOPP 파라미터 | `known_topp_params()` 필터와 경고, flag/boolean/list 처리 유지 |
| 실행 및 로그 | 기존 `run_command(command, task, cwd)` 유지 |
| 병렬 API | 공개 `run_multiple_commands()`는 계속 `bool` 반환 |
| 내부 병렬 결과 | `_run_multiple_command_results()`가 입력 명령 순서대로 `list[bool]` 반환 |
| TOPP 캐시 | 명령마다 hit 확인, miss만 실행, 성공한 miss만 publish |
| 진행 상태 | hit도 포함한 전체 파일을 기록하고 miss는 원래 파일 인덱스로 갱신 |
| Python / vendor 변환 | upstream의 `run_python()`, `convert_to_mzml()`, `stop()` 유지 |

초기화는 양쪽 상태를 함께 갖는다.

```python
self.workflow_dir = Path(workflow_dir)
self.progress = RunProgress(Path(workflow_dir))
self.step_cache = StepCache(self.workflow_dir)
self._step_cache_failed = False
```

캐시 디렉터리는 생성자에서 미리 만들지 않는다. 실제 publish 시 만든다. 따라서 캐시를 끄거나 결과를 저장할 필요가 없는 실행에 불필요한 디렉터리 쓰기가 추가되지 않는다.

## 3. bool 반환 계약과 명령별 결과를 동시에 유지

캐시는 어떤 파일이 성공했는지 알아야 하지만, 기존 호출자는 배치 전체의 성공 여부를 원한다. 공개 함수의 반환값을 리스트로 바꾸면 `[False, False]`도 Python에서 참으로 평가되어 실패를 성공으로 오인할 수 있다.

```python
def run_multiple_commands(self, commands, step=None) -> bool:
    return all(self._run_multiple_command_results(commands, step=step))
```

`run_topp()` 내부에서만 명령별 결과를 사용한다. 결과 저장은 완료 순서에 의존하지 않는다.

```python
results = [False] * num_commands

def run_and_track(index, cmd):
    # 실행 및 예외 처리 후
    results[index] = success
```

예를 들어 A가 느리게 성공하고 B가 빨리 실패해도 결과는 `[True, False]`다. 완료 순서대로 append하여 `[False, True]`가 되는 문제가 없어 A만 캐시에 저장된다. 스레드 안에서 예외가 발생하면 해당 결과는 `False`이며 파일 실패 상태와 문맥도 기록한다.

`run_topp()`의 최종 반환값도 `all(successes)`인 단일 bool이다. 전체 hit는 `True`다.

단일 입력의 실행 파일 시작 실패는 upstream처럼 예외를 전달한다. 여러 입력으로 시작한 배치는 hit 때문에 miss가 하나만 남아도 내부 배치 실행을 사용하므로, 시작 실패가 `False`로 집계되는 기존 의미를 유지한다.

## 4. cache hit가 있어도 파일 번호와 진행 상태 유지

캐시를 확인하면서 다음 목록을 함께 만든다.

```python
pending_commands = []  # 실제 실행할 명령
pending_meta = []      # 같은 위치의 캐시 digest/condition/output
pending_indices = []   # 전체 입력에서의 원래 파일 인덱스
cached_indices = []    # 캐시 복원이 완료된 원래 파일 인덱스
```

입력이 `A, B, C, D`이고 A/C가 hit이면 다음처럼 된다.

```python
cached_indices = [0, 2]
pending_indices = [1, 3]
pending_commands = [command_B, command_D]
```

진행 상태에는 전체 네 파일을 넣는다. 캐시 조회·복원 후 step을 생성하고, hit 파일은 곧바로 완료 처리한다.

```python
step = self.progress.start_step(
    tool if params_key == tool else f"{tool} ({params_key})",
    self._command_labels(input_output, n_processes),
    threads=threads_per_command,
    parallel=parallel_commands,
)
try:
    for index in cached_indices:
        self.progress.file_finished(step, index, ok=True)
    # miss 실행, 성공 결과 publish, bool 반환
finally:
    self.progress.end_step(step)
```

실행할 명령의 배열 인덱스와 진행 상태의 인덱스는 다를 수 있다.

```python
self.run_command(cmd, task=(step, file_indices[index]))
```

D가 실패하면 `file 4 of 4 (D)`가 기록된다. `file 2 of 2 (D)`로 바뀌지 않는다. 기존 stdout/stderr 수집, 종료 코드, `_log_failure_context()`를 그대로 이용한다.

전체 hit에도 step과 종료 시간이 기록된다. UI의 기존 상태 값과 호환되도록 hit는 `done`이며, 캐시 사용 여부는 `Cache HIT ...` 로그로 구분한다. 별도의 `cached` UI 상태는 추가하지 않았다. step 시간에는 앞서 수행한 캐시 조회·복사 시간이 포함되지 않는다.

## 5. 파라미터 필터와 실제 명령을 반영하는 해시

`known_topp_params(tool)`을 이용한 upstream 필터는 명령 생성 전에 유지했다. 설치된 도구가 모르는 저장 파라미터는 제거하고 경고한다. `custom_params`를 강제로 제거하지 않는 기존 동작도 유지한다.

다음 dict 병합만 해시하면 실제 CLI와 차이가 생긴다.

```python
merged_params = {"x": 1}
custom_params = {"x": 9}
effective_params = {**merged_params, **custom_params}  # {"x": 9}

# upstream이 생성하는 CLI는 두 인자를 모두 포함한다.
# ... -x 1 -x 9 -threads 1
```

`merged_params["x"]`를 2로 바꿔도 dict는 여전히 `{"x": 9}`다. 병합에서는 upstream의 CLI 생성 의미를 바꾸지 않고, **실제로 생성된 파라미터 argv**를 해시한다.

```python
params_start = len(command)  # input_output 인자 구성 직후
# upstream 방식대로 merged/custom/threads를 command에 추가
effective_params = {
    "io": cache_io,
    "argv": [str(v) for v in command[params_start:]],
}
```

따라서 아래 두 실행의 키는 다르다.

```text
-x 1 -x 9 -threads 1
-x 2 -x 9 -threads 1
```

flag가 실제로 포함되었는지, bool이 `true`/`false`로 변환되었는지, list가 어떻게 펼쳐졌는지, 중복 인자가 어떤 순서로 들어가는지도 반영한다. 제거된 파라미터는 argv에 없으므로 제거된 값만 변경해도 불필요한 miss가 발생하지 않는다.

`cache_io`에는 I/O 옵션 이름과 값의 순서도 넣는다. 같은 입력 목록이라도 `aux`를 `other`로 바꾸면 다른 명령으로 구분한다. 입력은 기존 설계의 basename 정책을 유지하며 출력은 전달된 전체 경로 문자열을 사용한다.

## 6. 실행 파일과 tool instance를 분리

```python
executor.run_topp(
    "FeatureFinderMetabo",
    input_output,
    tool_instance_name="feature-finder-second",
)
```

이때 파라미터/캐시 이름은 `feature-finder-second`지만 실제 실행 파일은 `FeatureFinderMetabo`다. StepCache의 `condition_hash()`에 선택 인자 `executable`을 추가했다.

```python
digest, condition = self.step_cache.condition_hash(
    tool=params_key,
    executable=tool,
    input_paths=inputs,
    output_paths=outputs,
    effective_params=params,
    threads=threads,
    upstream_keys=upstream_keys,
)
```

이제 instance 이름을 PATH에서 찾지 않고 실제 도구의 버전·바이너리 SHA-256을 확인한다. StepCache를 직접 사용하는 기존 호출자는 `executable`을 생략할 수 있다.

캐시 디렉터리 이름에는 `SHA256(tool 또는 instance 이름)`을 사용한다. 도구가 절대 경로여도 `cache_root / tool` 결합 때문에 캐시가 워크플로 밖에 만들어지지 않는다.

키 스키마는 2에서 **3**으로 올렸다. 출력 경로, 실제 argv, 실행 파일 구분 방식이 달라졌으므로 기존 키를 재사용하지 않는다. 기존 캐시 파일을 자동 삭제하지는 않는다.

## 7. 스레드 계산과 입력 인덱스

`_get_max_threads()`의 upstream 구현은 변경하지 않았다.

- 온라인: cgroup CPU quota가 있으면 우선하고, 없으면 online 설정을 해석한다.
- 로컬: 설정값을 기본으로 하며 params.json의 사용자 값을 반영한다.
- `auto` 등은 `resolve_thread_setting()`으로 해석한다.
- 잘못된 사용자 숫자는 1로 대체하며 executor에서 예산을 메모한다.

`run_topp()`의 스레드 배분도 전체 입력 개수를 기준으로 유지한다.

```python
parallel_commands = min(n_processes, max_threads)
threads_per_command = max(1, max_threads // parallel_commands)
```

hit를 제외한 뒤 남은 명령의 스레드 수를 다시 늘리지 않는다. 그렇지 않으면 cache hit 유무가 miss 명령의 실행 조건을 바꾸게 된다. 샘플을 추가하여 이 배분 자체가 달라지는 경우에는 스레드 수가 키에 포함되므로 기존 샘플도 miss일 수 있다.

공통 입력 처리에서는 바깥 루프의 `i`를 덮어쓰지 않도록 했다.

```python
idx = 0 if len(value) == 1 else i
entry = value[idx]
```

`database=[shared.fasta]` 뒤에 `in=[a, b]`가 있어도 두 번째 명령의 입력이 `a`로 되돌아가지 않는다.

## 8. 캐시 오류가 실행 성공 여부를 바꾸지 않도록 처리

캐시 조회/복원과 저장은 각각 `_lookup_step_cache()`, `_publish_step_cache()`로 분리했다. 캐시 I/O 및 처리 가능한 메타데이터 오류는 경고로 기록하고 실제 도구를 실행한다. 성공한 계산 뒤 캐시 저장이 실패해도 계산 결과를 실패로 바꾸지 않는다.

생산자 키 등록이 실패하면 downstream이 이전 키를 참조할 가능성이 있어, 캐시 오류 이후에는 해당 executor의 `_step_cache_failed`를 설정한다. 같은 executor의 나머지 실행은 캐시를 우회한다. publish할 출력이 누락되었거나 일반 파일이 아니어도 캐시를 중지한다. 다음 새 executor에서는 다시 캐시 사용을 시도한다.

캐시 파일의 checksum 불일치나 누락은 정상적인 miss로 처리하여 재계산한다. 잘못된 manifest 구조, 다른 digest, 예상과 다른 번호의 캐시 파일 참조도 hit로 인정하지 않는다.

캐시는 정상 종료한 명령에 대해서만 publish한다.

```python
for success, meta in zip(successes, pending_meta):
    if success and meta is not None:
        self._publish_step_cache(params_key, meta)
return all(successes)
```

## 9. 유지되는 정책과 검증 범위의 한계

입력의 **내용이 아니라 basename**으로 식별하는 기존 StepCache 정책은 유지했다. 따라서 모든 가능한 입력 변경을 자동 감지하는 캐시는 아니다.

- 같은 이름의 mzML/FASTA 내용을 바꾸거나 다른 디렉터리의 동명 파일로 교체하면 hit일 수 있다. 이름 변경, 해당 캐시 제거 또는 캐시 비활성화가 필요하다.
- 키 생성은 입력 내용·크기·mtime을 읽지 않으며 입력 존재도 검사하지 않는다. 입력이 없어도 기존 캐시가 일치하면 결과를 복원할 수 있다.
- `producers.json`의 의존성 연결도 basename 기준이며 프로세스 재시작 후 다시 읽는다. 동명 파일 충돌은 이 정책의 제한이다.
- 캐시를 껐다가 켜도 기존 엔트리는 남는다. 꺼 둔 동안 동명 입력 내용을 바꿨다면 예전 결과가 다시 재사용될 수 있다.
- 실제 실행 파일 자체의 교체는 감지하지만, adapter가 실행하는 별도 외부 바이너리의 내용, 공유 라이브러리, 환경 변수, 리소스 파일 변경을 자동 추적하지 않는다.
- `input_output`의 `out*` 옵션만 출력으로 인식한다. 별도의 로그/부수 출력이나 파라미터 안에서만 지정한 파일까지 자동으로 복원하지 않는다.
- 출력의 전체 경로가 바뀌면 miss다. multi-run의 새 결과 디렉터리 사이 재사용보다 경로에 따른 동작 차이를 구분하는 쪽을 택했다.
- 동일 워크플로 캐시에 여러 프로세스가 동시에 publish하는 상황의 트랜잭션/잠금은 이번 병합 범위에 포함하지 않는다.
- Python 도구를 `run_python()`으로 실행하는 경로는 이 캐시 대상이 아니다.

다음 설정으로 기존 계산 경로를 사용할 수 있다.

```json
{"step-cache-enabled": false}
```

## 10. 회귀 테스트

기존 upstream 테스트 파일은 수정하지 않았다. StepCache 테스트의 mock은 upstream의 `task` 인자를 받도록 조정하고, 실제 subprocess를 사용하는 통합 테스트를 추가했다. TOPP 대신 작은 Python 프로그램을 실행하여 Windows와 Linux 모두에서 stdout/stderr·종료 코드·PID·진행 상태 경로를 검증한다.

주요 검증 항목:

| 시나리오 | 확인 내용 |
| --- | --- |
| 전체 hit | 도구 실행 없음, 출력 복원, 전체 파일 done, step 종료 |
| hit / 느린 성공 / hit / 빠른 실패 | 원래 파일 번호, 실패 코드·출력, 성공한 파일만 캐시 저장 |
| 실패 후 재시도 | 성공 파일은 hit, 실패 파일만 다시 실행 |
| 배치에서 miss 하나만 남은 뒤 시작 실패 | 예외를 배치 실패 `False`로 집계, 원래 파일 번호 유지 |
| 캐시 off | 조회·저장 호출 없음, 매번 실행, 진행 상태 유지 |
| 저장/복원 I/O 오류 | 계산은 성공, 이후 단계에서 캐시 우회 |
| 파라미터 변경 | 실제 중복 CLI 값이 바뀌면 miss, 제거된 값만 바뀌면 hit |
| instance 이름 + 바이너리 교체 | 실제 실행 파일 identity를 사용, 바이너리 변경 시 miss |
| 공통 입력 + 여러 샘플 | 입력과 출력의 순서가 정확히 대응 |
| manifest 손상 / 경로 | 손상은 miss, 절대 도구 경로도 캐시 root 내부에 저장 |
| upstream 전용 테스트 | 스레드 설정, 진행 상태, pickle, flags, 버전 drift, Python 실패, vendor 변환 |

실행 명령과 최종 수치는 아래 검증 결과에 기록한다. 실제 OpenMS 도구와 실데이터 전체 워크플로의 end-to-end 실행을 대신하는 검증은 아니다.

### 최종 검증 결과

Windows / Python 3.11:

```powershell
python -m pytest tests/test_step_cache.py tests/test_topp_flag_parameters.py tests/test_topp_version_drift.py tests/test_parameter_integrity.py tests/test_command_executor_run_python.py tests/test_vendor_conversion.py tests/test_tasks.py -q --tb=short
# 174 passed, 5 skipped
```

WSL Ubuntu 24.04 / 전용 임시 Python 환경:

```bash
python -m pytest tests/test_step_cache.py tests/test_run_progress.py tests/test_topp_flag_parameters.py tests/test_topp_version_drift.py tests/test_parameter_integrity.py tests/test_command_executor_run_python.py tests/test_vendor_conversion.py -q --tb=short
# 177 passed, 1 skipped
```

두 테스트 집합은 상당 부분 중복된다. 두 수치를 합산하여 고유 테스트 수로 해석하면 안 된다. Windows 집합에는 workflow task 테스트가 있고, Linux 집합에는 POSIX 실행 파일을 사용하는 upstream 진행 상태 테스트가 있다. skip은 통과로 계산하지 않았다.

추가 확인:

- `git diff --check` 통과.
- 수정된 Python 파일의 `compileall` 통과.
- CommandExecutor의 충돌 마커 제거 확인.
- `upstream/main`과 AST 비교 결과 `_get_max_threads`, `run_command`, `_log_failure_context`, `_command_labels`, `_stream_output`, `stop`, `run_python`, `convert_to_mzml`의 구현이 동일함을 확인.

이 검증은 병합으로 인한 실행 제어·진행 상태·캐시 연동 회귀를 대상으로 한다. 전체 저장소 CI, GUI 수동 실행, 실제 TOPP 바이너리와 실데이터 분석까지 모두 실행했다는 의미는 아니다.
