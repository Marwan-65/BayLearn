#include "headers.h"

/* Modify this file as needed*/
int remainingtime;


bool running = false;
void handler(int signum);
int main(int agrc, char *argv[])
{

    initClk();
    signal(SIGCONT,handler);
    printf("pid : %d started at %d\n",getpid(),getClk());
    fflush(stdout);

    //TODO The process needs to get the remaining time from somewhere
    //remainingtime = ??;

    remainingtime = atoi(argv[0]);


    int prev_clk = getClk();

    while(remainingtime > 0)
    {
        prev_clk = getClk();
        fflush(stdout);
        while(prev_clk == getClk())
        {  
        }
        remainingtime--;
        fflush(stdout);
        signal(SIGCONT,handler);
        // remainingtime = ??;
    }

    kill(getppid(),SIGUSR1);

    destroyClk(false);
    exit(0);
    return 0;
}

void handler(int signum)
{
    int currtime = getClk();
    while(currtime == getClk());
    signal(SIGCONT,SIG_DFL);
    kill(getpid(),SIGCONT);
}
