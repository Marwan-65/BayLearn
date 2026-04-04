
#pragma once
#include "process_table.c"
#include "priority_queue.h"


typedef struct hpf {
    Process* running;
    Pri_Queue queue;
    bool (*add)(void*, Process*);
    Process* (*deq)(void*);
    void (*Run)(void*);
    void (*terminate)(int);
}HPF;

static HPF hpf_default;

int lastSwitch;

void terminated(int signum);


bool hpf_add(void* ptr,Process* toinsert)
{
    HPF* this = (HPF*) ptr;
    if(!found(root, toinsert->Id)){
        Memory *temp = occupyMemory(root, toinsert);
        if (temp == NULL)
            return false;
        fprintf(mFile, "At time %d allocated %d bytes for process %d from %d to %d\n", getClk() , toinsert->memoryBlock->size, toinsert->Id, toinsert->memoryBlock->startAddress, toinsert->memoryBlock->startAddress + toinsert->memoryBlock->size - 1);
        fflush(mFile);
    }
    Pri_Node* node = (Pri_Node*) malloc(sizeof(Pri_Node));
    node->data = toinsert;
    node->pri = toinsert->pri;
    this->queue.insert(&(this->queue.start),node);
    return true;
}

Process* hpf_deq(void* ptr)
{
    HPF* this = (HPF*) ptr;
    Pri_Node* node = this->queue.dequeue(&(this->queue.start));
    return node->data;
}

void hpf_run(void* ptr)
{
    HPF* this = (HPF*) ptr;
    if(this->queue.is_empty(&(this->queue)) && this->running == NULL)
    {
        if(getClk()>0)
            IdleTime++;
        return;
    }

    if (this->running != NULL) //suspends the process if there is higher piority 
    {
        if (!this->queue.is_empty(&(this->queue)) && this->queue.start->data->pri < this->running->pri) {
            int preemptor_id  = this->queue.start->data->Id;
            int preemptor_pri = this->queue.start->data->pri;
            int current_pri   = this->running->pri;
            this->running->rem_time -= (getClk() - lastSwitch);
            PCB* suspended_pcb = process_table.update_pcb(this->running->Id,0,this->running->rem_time);
            fprintf(pFile, "At\ttime\t%d\tprocess\t%d\tstopped\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\n",getClk(),this->running->Id,this->running->AT,this->running->RT,this->running->rem_time,suspended_pcb->wait_t);
            fprintf(rFile, "At\ttime\t%d\tprocess\t%d\tstopped\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\treason: PREEMPTED_BY_HIGHER_PRIORITY — process %d (priority %d) entered the ready queue with a higher priority than this process (priority %d); lower value = higher priority in HPF, so it takes the CPU immediately\n",getClk(),this->running->Id,this->running->AT,this->running->RT,this->running->rem_time,suspended_pcb->wait_t,preemptor_id,preemptor_pri,current_pri);
            fflush(pFile);
            fflush(rFile);
            hpf_add(this,this->running);
            kill(suspended_pcb->pid,SIGSTOP);
        }
    }

    if ((this->running != NULL && ((!this->queue.is_empty(&(this->queue)) && this->queue.start->data->pri < this->running->pri) || this->running->rem_time == 0 )) || this->running == NULL) 
    {
        bool idle = (this->running == NULL);
        this->running = this->deq(this);

        if(this->running != NULL)
        {
            PCB* running_pcb = process_table.update_pcb(this->running->Id,1,this->running->rem_time);
            running_pcb->wait_t = getClk() - this->running->AT - (this->running->RT - this->running->rem_time);
            if(this->running->RT == this->running->rem_time) {
                int process_fork = fork();
                if(process_fork == 0)
                {
                    char run_time[8] = "";
                    sprintf(run_time, "%d", running_pcb->rem_t);
                    char *args_sch[]={run_time,NULL};
                    execv("./process.out", args_sch);
                }
                running_pcb->pid = process_fork;
                fprintf(pFile, "At\ttime\t%d\tprocess\t%d\tstarted\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\n",getClk(),this->running->Id,this->running->AT,this->running->RT,this->running->rem_time,running_pcb->wait_t);
                fprintf(rFile, "At\ttime\t%d\tprocess\t%d\tstarted\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\treason: FIRST_RUN — highest priority (value %d, lower=higher) among all arrived processes; entered CPU for the first time after waiting %d time unit(s) since arrival at t=%d\n",getClk(),this->running->Id,this->running->AT,this->running->RT,this->running->rem_time,running_pcb->wait_t,this->running->pri,running_pcb->wait_t,this->running->AT);
            }
            else
            {
                fprintf(pFile, "At\ttime\t%d\tprocess\t%d\tresumed\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\n",getClk(),this->running->Id,this->running->AT,this->running->RT,this->running->rem_time,running_pcb->wait_t);
                fprintf(rFile, "At\ttime\t%d\tprocess\t%d\tresumed\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\treason: RESUMED — the process that preempted this one no longer holds the highest priority; this process (priority %d) is now the highest-priority process in the ready queue; %d time unit(s) remaining out of original %d\n",getClk(),this->running->Id,this->running->AT,this->running->RT,this->running->rem_time,running_pcb->wait_t,this->running->pri,this->running->rem_time,this->running->RT);
                kill(running_pcb->pid,SIGCONT);
            }
            fflush(pFile);
            fflush(rFile);
            lastSwitch = getClk();
        }
        else {
            if(idle)
                IdleTime++;
        }
    }
}

static void create_default_hpf()
{
    hpf_default.running = NULL;
    hpf_default.queue = default_pri_queue;
    hpf_default.add = &hpf_add;
    hpf_default.Run = &hpf_run;
    hpf_default.deq = &hpf_deq;
    hpf_default.terminate = &terminated;
    root = createMemoryBlock(0, 1024);

    pFile = fopen("Scheduler_log.txt", "w");
    mFile = fopen("Memory_log.txt", "w");
    rFile = fopen("reason_log.txt", "w");
}

void terminated(int signum) {
    hpf_default.running->rem_time = 0;
    PCB* finished_pcb = process_table.remove(hpf_default.running->Id);
    Process* finished = hpf_default.running;

    if(finished_pcb != NULL)
    {
        int TA = getClk() - hpf_default.running->AT;
        float WTA = (float)TA / hpf_default.running->RT;
        TWT += finished_pcb->wait_t;
        TWTT += WTA;
        N++;
        fprintf(mFile, "At time %d freed %d bytes from process %d from %d to %d\n", getClk(), finished->memoryBlock->size, finished->Id, finished->memoryBlock->startAddress, finished->memoryBlock->startAddress + finished->memoryBlock->size - 1);
        fflush(mFile);
        freeMemory(root, finished->Id);
        fprintf(pFile, "At\ttime\t%d\tprocess\t%d\tfinished\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\tTA\t%d\tWTA\t%f\n",getClk(),hpf_default.running->Id,hpf_default.running->AT,hpf_default.running->RT,0,finished_pcb->wait_t,TA,WTA);
        fprintf(rFile, "At\ttime\t%d\tprocess\t%d\tfinished\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\tTA\t%d\tWTA\t%f\treason: COMPLETED — burst of %d time unit(s) fully consumed; no higher-priority process was present to interrupt this final run\n",getClk(),hpf_default.running->Id,hpf_default.running->AT,hpf_default.running->RT,0,finished_pcb->wait_t,TA,WTA,hpf_default.running->RT);
        fflush(pFile);
        fflush(rFile);
        free(finished_pcb);
    }
    hpf_default.running = NULL;
}