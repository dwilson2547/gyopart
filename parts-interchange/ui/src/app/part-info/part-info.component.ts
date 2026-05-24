import { Component, ViewChild } from '@angular/core';
import { MessageQueues, MessageService } from 'src/services/message.service';
import { PartsService, CompatibleCarsRequest } from 'src/services/parts.service';
import { filter, merge, startWith, switchMap, map } from 'rxjs';
import { NONE_TYPE } from '@angular/compiler';
import { MatPaginator } from '@angular/material/paginator';
import { MatSort } from '@angular/material/sort';

@Component({
  selector: 'app-part-info',
  templateUrl: './part-info.component.html',
  styleUrls: ['./part-info.component.scss'],
  providers: [PartsService]
})
export class PartInfoComponent {

  partId = 0;
  part: any = null;
  compatible_cars: any = null;
  resultsLength = 0;
  img_url: any = null;
  isLoadingResults: boolean = false;
  img_caption = '';
  displayedColumns = ['year','make','model','engine','trim']

  @ViewChild(MatPaginator) paginator!: MatPaginator;
  @ViewChild(MatSort) sort!: MatSort;

  constructor(private messageService: MessageService, private partService: PartsService) {
    this.messageService.getMessage().pipe(filter((event) => event.getQueue() == MessageQueues.PART_SEARCH_QUEUE)).subscribe((msg: any) => {
      this.partId = msg.getPayload()['id'];
      this.part = msg.getPayload();
      this.img_url = '/part-images/' + this.part.images[0].image.bucket_path
      this.img_caption = this.part.images[0].part_image_text
      this.initializeTablePagingSorting()
    })
  }

  initializeTablePagingSorting() {
    this.sort.sortChange.subscribe(() => {
      this.paginator.pageIndex = 0;
    });

    merge(this.sort.sortChange, this.paginator.page)
      .pipe(
        startWith({}),
        switchMap((val: any) => {
          this.isLoadingResults = true;
          console.log(val);
          return this.loadData(this.sort.active, this.sort.direction, this.paginator.pageIndex, this.paginator.pageSize);
        }),
        map(data => {
          this.isLoadingResults = false;
          return data;
        })
      ).subscribe(data => {
        this.compatible_cars = data['items'];
        this.resultsLength = data['total']
      })
  }

  loadData(sortCol: string, sortDir: string, pageIndex: number, pageSize: number) {
    let ccr = new CompatibleCarsRequest(this.partId, pageIndex, pageSize, sortCol, sortDir)
    return this.partService.get_compatible_cars(this.partId, ccr);
  }

}
